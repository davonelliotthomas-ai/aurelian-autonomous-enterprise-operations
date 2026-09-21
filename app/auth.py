from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated
import asyncio, jwt, httpx
from functools import lru_cache
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import settings
from .database import set_tenant_context
from .secrets import secrets

bearer=HTTPBearer(auto_error=False)
ROLE_LEVEL={"viewer":0,"operator":1,"admin":2,"executive":3}

@dataclass
class Principal:
    sub:str; tenant_id:str; role:str; scopes:set[str]; mfa:bool

def create_demo_token(sub:str,tenant_id:str,role:str,mfa:bool=True)->str:
    if role not in ROLE_LEVEL: raise ValueError("invalid role")
    now=datetime.now(timezone.utc); scopes={"viewer":["read"],"operator":["read","operate"],"admin":["read","operate","approve:team"],"executive":["read","operate","approve:team","approve:executive"]}[role]
    return jwt.encode({"sub":sub,"tenant_id":tenant_id,"role":role,"scope":" ".join(scopes),"mfa":mfa,"iss":settings.jwt_issuer,"aud":settings.jwt_audience,"iat":now,"exp":now+timedelta(hours=8)},secrets.get("JWT_SECRET"),algorithm="HS256")

def _principal(payload:dict)->Principal:
    role=str(payload.get("role") or (payload.get("roles") or ["viewer"])[0]); tenant=str(payload.get("tenant_id") or payload.get("tid") or "")
    if role not in ROLE_LEVEL or not tenant: raise HTTPException(403,"Token lacks recognized tenant/role claims")
    scope=payload.get("scope",""); scopes=set(scope.split()) if isinstance(scope,str) else set(scope or [])
    amr=payload.get("amr",[]); mfa=bool(payload.get("mfa")) or "mfa" in amr
    p=Principal(str(payload.get("sub","unknown")),tenant,role,scopes,mfa); set_tenant_context(tenant); return p

_jwks_uri_cache: str | None = None
_jwks_uri_lock = asyncio.Lock()

@lru_cache(maxsize=8)
def _jwk_client(jwks_uri: str):
    # Persistent client retains PyJWT's JWK-set/key cache across requests.
    return jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=300)

async def _resolve_jwks_uri() -> str:
    global _jwks_uri_cache
    if settings.oidc_jwks_url:
        return settings.oidc_jwks_url
    if _jwks_uri_cache:
        return _jwks_uri_cache
    async with _jwks_uri_lock:
        if _jwks_uri_cache:
            return _jwks_uri_cache
        issuer=settings.oidc_issuer.rstrip("/")
        async with httpx.AsyncClient(timeout=3) as c:
            r=await c.get(issuer+"/.well-known/openid-configuration")
            r.raise_for_status()
            _jwks_uri_cache=str(r.json()["jwks_uri"])
        return _jwks_uri_cache

async def _decode_oidc(token:str)->dict:
    issuer=settings.oidc_issuer.rstrip("/")
    jwks=await _resolve_jwks_uri()
    def verify():
        client=_jwk_client(jwks)
        key=client.get_signing_key_from_jwt(token).key
        return jwt.decode(token,key,algorithms=["RS256","ES256"],audience=settings.oidc_audience or None,issuer=issuer,options={"verify_aud":bool(settings.oidc_audience)})
    return await asyncio.to_thread(verify)

async def current_principal(credentials:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)])->Principal:
    if not credentials:
        # Even in public-demo mode, protected APIs require a signed bearer token.
        # The demo-token endpoint is the only bootstrap path; header-based role
        # impersonation is intentionally not supported.
        raise HTTPException(401,"Bearer token required")
    try:
        if settings.oidc_issuer:
            return _principal(await _decode_oidc(credentials.credentials))
        payload=jwt.decode(credentials.credentials,secrets.get("JWT_SECRET"),algorithms=["HS256"],audience=settings.jwt_audience,issuer=settings.jwt_issuer)
        return _principal(payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401,f"Invalid bearer token: {type(e).__name__}")

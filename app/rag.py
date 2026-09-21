from __future__ import annotations
import hashlib, json, math, re, time
from collections import Counter, OrderedDict
import httpx
from .database import db,set_tenant_context
from .config import settings
from .security import context_is_usable,classify_untrusted_input_async
from .secrets import secrets

TOKEN_RE=re.compile(r"[a-zA-Z0-9_\-]+")
_CACHE=OrderedDict()
_REDIS=None
COLLECTION="aurelian_documents"
DIM=128

def tokens(s:str): return [x.lower() for x in TOKEN_RE.findall(s) if len(x)>1]

def bm25ish(query:str,text:str)->float:
    q=Counter(tokens(query)); d=Counter(tokens(text)); n=max(len(tokens(text)),1)
    return sum((1+math.log1p(d[t]))*(1+math.log1p(q[t])) for t in q if t in d)/math.sqrt(n)

def dense_hash(text:str,dim:int=DIM)->list[float]:
    """Deterministic offline embedding for the public demo.
    Qdrant integration is real; production adapters can replace this encoder with enterprise embeddings.
    """
    v=[0.0]*dim
    for t in tokens(text):
        h=int(hashlib.sha256(t.encode()).hexdigest(),16); idx=h%dim; sign=1 if (h>>8)&1 else -1; v[idx]+=sign
    norm=math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/norm for x in v]

def cosine(a,b): return sum(x*y for x,y in zip(a,b))

def _local_cache_get(key:str):
    val=_CACHE.get(key)
    if not val:return None
    if time.time()-val[0]>=60:
        _CACHE.pop(key,None); return None
    _CACHE.move_to_end(key)
    return val[1]

def _local_cache_set(key:str,value):
    _CACHE[key]=(time.time(),value); _CACHE.move_to_end(key)
    while len(_CACHE)>settings.local_cache_max_entries:
        _CACHE.popitem(last=False)

async def _redis_client():
    global _REDIS
    if not settings.redis_url:return None
    if _REDIS is None:
        import redis.asyncio as redis
        password=secrets.get(settings.redis_password_secret, "")
        _REDIS=redis.from_url(settings.redis_url,decode_responses=True,password=password or None)
    return _REDIS

async def close_backends():
    global _REDIS
    if _REDIS is not None:
        await _REDIS.aclose(); _REDIS=None

async def _cache_get(key:str):
    if settings.redis_url:
        try:
            r=await _redis_client(); val=await r.get("rag:"+key)
            return json.loads(val) if val else None
        except Exception:
            pass
    return _local_cache_get(key)

async def _cache_set(key:str,value):
    if settings.redis_url:
        try:
            r=await _redis_client(); await r.setex("rag:"+key,60,json.dumps(value,default=str)); return
        except Exception:
            pass
    _local_cache_set(key,value)

def _qdrant_headers()->dict[str,str]:
    if not settings.qdrant_url:return {}
    key=secrets.get(settings.qdrant_api_key_secret, "")
    return {"api-key":key} if key else {}

async def _qdrant_ensure():
    if not settings.qdrant_url:return
    headers=_qdrant_headers()
    async with httpx.AsyncClient(timeout=2,headers=headers) as c:
        r=await c.get(f"{settings.qdrant_url}/collections/{COLLECTION}")
        if r.status_code==404:
            rr=await c.put(f"{settings.qdrant_url}/collections/{COLLECTION}",json={"vectors":{"size":DIM,"distance":"Cosine"}}); rr.raise_for_status()
        else:
            r.raise_for_status()

async def _qdrant_upsert(doc_id:int,tenant_id:str,title:str,content:str,environment:str,service:str,trust_level:str):
    if not settings.qdrant_url:return
    try:
        await _qdrant_ensure(); vector=dense_hash(title+" "+content)
        async with httpx.AsyncClient(timeout=2,headers=_qdrant_headers()) as c:
            r=await c.put(f"{settings.qdrant_url}/collections/{COLLECTION}/points?wait=true",json={"points":[{"id":doc_id,"vector":vector,"payload":{"tenant_id":tenant_id,"title":title,"content":content,"environment":environment,"service":service,"trust_level":trust_level}}]}); r.raise_for_status()
    except Exception:
        pass

async def ingest(tenant_id:str,title:str,content:str,environment="production",service="general",trust_level="trusted"):
    set_tenant_context(tenant_id)
    from .audit import utcnow
    # Untrusted knowledge cannot promote itself into the trusted retrieval set.
    # High-risk prompt-injection content is quarantined even if a caller labels
    # it trusted. Human review can later re-ingest a sanitized document.
    risk=await classify_untrusted_input_async(content)
    effective_trust="untrusted" if risk.risk=="high" else trust_level
    now=utcnow(); doc_id=await db.insert_returning_id("INSERT INTO documents(tenant_id,title,content,environment,service,trust_level,updated_at,created_at) VALUES(?,?,?,?,?,?,?,?)",(tenant_id,title.strip(),content.strip(),environment,service,effective_trust,now,now))
    await _qdrant_upsert(doc_id,tenant_id,title,content,environment,service,effective_trust); return doc_id

async def _qdrant_candidates(tenant_id:str,query:str,environment:str,service:str|None,limit:int):
    if not settings.qdrant_url:return {}
    try:
        await _qdrant_ensure(); must=[{"key":"tenant_id","match":{"value":tenant_id}},{"key":"environment","match":{"any":[environment,"all"]}},{"key":"trust_level","match":{"any":["trusted","verified"]}}]
        if service: must.append({"key":"service","match":{"any":[service,"general","all"]}})
        async with httpx.AsyncClient(timeout=2,headers=_qdrant_headers()) as c:
            r=await c.post(f"{settings.qdrant_url}/collections/{COLLECTION}/points/search",json={"vector":dense_hash(query),"limit":limit*3,"with_payload":True,"filter":{"must":must}}); r.raise_for_status()
            return {int(x["id"]):float(x["score"]) for x in r.json().get("result",[])}
    except Exception:return {}

async def search(tenant_id:str,query:str,environment="production",service:str|None=None,limit=5,threshold:float|None=None):
    set_tenant_context(tenant_id)
    threshold=settings.retrieval_threshold if threshold is None else threshold
    cache_key=hashlib.sha256(f"{tenant_id}|{query.lower()}|{environment}|{service}|{limit}".encode()).hexdigest()
    cached=await _cache_get(cache_key)
    if cached:return {**cached,"cache":"hit"}
    docs=await db.fetchall("SELECT * FROM documents WHERE tenant_id=? ORDER BY id DESC",(tenant_id,)); qv=dense_hash(query); qdrant=await _qdrant_candidates(tenant_id,query,environment,service,limit); scored=[]
    for d in docs:
        if not context_is_usable(d,environment,service):continue
        text=d["title"]+" "+d["content"]; sparse=bm25ish(query,text); local_dense=cosine(qv,dense_hash(text)); dense=qdrant.get(int(d["id"]),local_dense); metadata=0.12 if service and d.get("service")==service else 0; phrase=0.15 if query.lower() in text.lower() else 0
        combined=0.48*min(sparse/4,1)+0.37*max(dense,0)+metadata+phrase
        if combined>=threshold:scored.append({**d,"score":round(combined,4),"sparse":round(sparse,4),"dense":round(dense,4),"rerank":round(metadata+phrase,4)})
    scored.sort(key=lambda x:x["score"],reverse=True); result={"matches":scored[:limit],"strategy":"hybrid-bm25+dense+rerank","vector_backend":"qdrant" if qdrant else "local-fallback","threshold":threshold}
    await _cache_set(cache_key,result); return {**result,"cache":"miss"}

from __future__ import annotations
import logging
import asyncio
import hashlib
import hmac
import json
from collections import defaultdict
from datetime import datetime, timezone
import httpx
from .config import settings
from .secrets import secrets
from .database import db, audit_db, set_tenant_context

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _event_body(tenant_id: str, actor: str, event_type: str, payload: dict, prev_hash: str, created_at: str) -> str:
    envelope={
        "v":1,
        "tenant_id":tenant_id,
        "actor":actor,
        "event_type":event_type,
        "payload":payload,
        "prev_hash":prev_hash,
        "created_at":created_at,
    }
    return canonical(envelope)

def _signed_event(tenant_id: str, actor: str, event_type: str, payload: dict, prev_hash: str, created_at: str):
    body = _event_body(tenant_id, actor, event_type, payload, prev_hash, created_at)
    event_hash = hashlib.sha256(body.encode()).hexdigest()
    signature = hmac.new(
        secrets.get("AUDIT_SIGNING_KEY").encode(),
        event_hash.encode(),
        hashlib.sha256,
    ).hexdigest()
    return event_hash, signature


_sqlite_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def append_audit(tenant_id: str, actor: str, event_type: str, payload: dict) -> dict:
    """Append one audit event using the dedicated audit-writer identity.

    PostgreSQL uses a tenant-scoped advisory transaction lock so two API workers
    cannot race while deriving the hash-chain head. The audit writer has only
    SELECT+INSERT on audit_events and cannot UPDATE/DELETE/TRUNCATE/ALTER it.
    """
    set_tenant_context(tenant_id)
    created_at = utcnow()

    if audit_db.is_postgres:
        async with audit_db.pg_pool.acquire() as conn:
            async with conn.transaction():
                await audit_db._pg_prepare(conn)
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", tenant_id)
                row = await conn.fetchrow(
                    "SELECT event_hash FROM audit_events WHERE tenant_id=$1 ORDER BY id DESC LIMIT 1",
                    tenant_id,
                )
                prev_hash = row["event_hash"] if row else "GENESIS"
                event_hash, signature = _signed_event(
                    tenant_id, actor, event_type, payload, prev_hash, created_at
                )
                event_id = await conn.fetchval(
                    """
                    INSERT INTO audit_events(
                        tenant_id,actor,event_type,payload_json,prev_hash,event_hash,signature,created_at
                    ) VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
                    """,
                    tenant_id,
                    actor,
                    event_type,
                    canonical(payload),
                    prev_hash,
                    event_hash,
                    signature,
                    created_at,
                )
    else:
        async with _sqlite_locks[tenant_id]:
            last = await audit_db.fetchone(
                "SELECT event_hash FROM audit_events WHERE tenant_id=? ORDER BY id DESC LIMIT 1",
                (tenant_id,),
            )
            prev_hash = last["event_hash"] if last else "GENESIS"
            event_hash, signature = _signed_event(
                tenant_id, actor, event_type, payload, prev_hash, created_at
            )
            event_id = await audit_db.execute(
                "INSERT INTO audit_events(tenant_id,actor,event_type,payload_json,prev_hash,event_hash,signature,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (tenant_id, actor, event_type, canonical(payload), prev_hash, event_hash, signature, created_at),
            )

    event = {
        "id": int(event_id),
        "tenant_id": tenant_id,
        "actor": actor,
        "event_type": event_type,
        "payload": payload,
        "prev_hash": prev_hash,
        "event_hash": event_hash,
        "signature": signature,
        "created_at": created_at,
    }
    if settings.siem_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                await client.post(settings.siem_webhook_url, json=event)
        except Exception:
            # Audit persistence remains authoritative locally even when the optional
            # SIEM transport is unavailable, but the delivery failure must be visible.
            logger.warning("SIEM webhook delivery failed", exc_info=True)
    return event


async def verify_chain(tenant_id: str) -> dict:
    set_tenant_context(tenant_id)
    events = await audit_db.fetchall(
        "SELECT * FROM audit_events WHERE tenant_id=? ORDER BY id", (tenant_id,)
    )
    prev = "GENESIS"
    for e in events:
        payload = json.loads(e["payload_json"])
        body = _event_body(tenant_id, e["actor"], e["event_type"], payload, prev, e["created_at"])
        expected = hashlib.sha256(body.encode()).hexdigest()
        sig = hmac.new(
            secrets.get("AUDIT_SIGNING_KEY").encode(),
            expected.encode(),
            hashlib.sha256,
        ).hexdigest()
        if (
            expected != e["event_hash"]
            or not hmac.compare_digest(sig, e["signature"])
            or e["prev_hash"] != prev
        ):
            return {"valid": False, "events": len(events), "failed_id": e["id"]}
        prev = e["event_hash"]
    return {"valid": True, "events": len(events), "head": prev}

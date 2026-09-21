"""Async database facade with tenant-safe PostgreSQL pooling.

Production path:
- PostgreSQL via asyncpg
- credentials supplied separately from DSN through the secret provider
- tenant context is applied with transaction-scoped set_config(..., true)
- every pooled connection is sanitized with DISCARD ALL before reuse

Demo/tests:
- SQLite fallback for portable local tests
"""
from __future__ import annotations
import asyncio
import sqlite3
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterable
from .config import settings
from .secrets import secrets

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
TENANT_CONTEXT: ContextVar[str | None] = ContextVar("aurelian_tenant", default=None)


def set_tenant_context(tenant_id: str | None):
    TENANT_CONTEXT.set(tenant_id)


class Database:
    def __init__(self, url: str | None = None, password_secret: str | None = None):
        self.url = url or settings.database_url
        self.password_secret = password_secret
        self.pg_pool = None
        self.sqlite_path = self.url.removeprefix("sqlite:///") if self.url.startswith("sqlite:///") else ""

    @property
    def is_postgres(self) -> bool:
        return self.url.startswith("postgresql://") or self.url.startswith("postgres://")

    async def _pg_reset(self, conn):
        # statement_cache_size=0 is intentional: DISCARD ALL clears all session
        # state, prepared statements and tenant settings before pool reuse.
        await conn.execute("DISCARD ALL")

    async def connect(self):
        if self.is_postgres:
            import asyncpg
            password = secrets.get(self.password_secret, "") if self.password_secret else None
            self.pg_pool = await asyncpg.create_pool(
                self.url,
                password=password or None,
                min_size=1,
                max_size=10,
                command_timeout=10,
                statement_cache_size=0,
                reset=self._pg_reset,
            )
            # The runtime application role is intentionally not permitted to
            # create or alter schema. Schema/migrations are owned by the
            # short-lived migration/bootstrap role.
            async with self.pg_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        else:
            if settings.environment not in {"demo", "test"}:
                raise RuntimeError("SQLite fallback is restricted to explicit demo/test environments")
            Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            await self.init_schema()

    async def close(self):
        if self.pg_pool:
            await self.pg_pool.close()

    async def init_schema(self):
        if self.is_postgres:
            raise RuntimeError("PostgreSQL schema changes are forbidden to runtime roles")
        sql = SCHEMA_PATH.read_text()
        def _run():
            con = sqlite3.connect(self.sqlite_path)
            try:
                con.executescript(sql)
            finally:
                con.close()
        await asyncio.to_thread(_run)

    async def _pg_prepare(self, conn):
        tenant = TENANT_CONTEXT.get()
        if tenant:
            # Equivalent to SET LOCAL: third parameter true makes the setting
            # transaction-local and PostgreSQL automatically discards it at
            # COMMIT/ROLLBACK. Pool reset provides a second safety boundary.
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        if self.is_postgres:
            pg_sql = _pg_placeholders(sql)
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await self._pg_prepare(conn)
                    status = await conn.execute(pg_sql, *tuple(params))
                    try:
                        return int(status.split()[-1])
                    except Exception:
                        return 0
        def _run():
            con = sqlite3.connect(self.sqlite_path)
            try:
                cur = con.execute(sql, tuple(params))
                con.commit()
                return int(cur.lastrowid or cur.rowcount or 0)
            finally:
                con.close()
        return await asyncio.to_thread(_run)


    async def insert_returning_id(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Execute an INSERT and return its generated integer id explicitly.

        Callers must pass an INSERT without a RETURNING clause. This avoids the
        old heuristic that searched SQL text for the word RETURNING.
        """
        if self.is_postgres:
            pg_sql = _pg_placeholders(sql).rstrip().rstrip(";") + " RETURNING id"
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await self._pg_prepare(conn)
                    value = await conn.fetchval(pg_sql, *tuple(params))
                    return int(value)
        return await self.execute(sql, params)

    async def fetchone_write(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        """Execute one write statement with RETURNING and return the row atomically."""
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await self._pg_prepare(conn)
                    row = await conn.fetchrow(_pg_placeholders(sql), *tuple(params))
                    return dict(row) if row else None
        def _run():
            con = sqlite3.connect(self.sqlite_path)
            con.row_factory = sqlite3.Row
            try:
                row = con.execute(sql, tuple(params)).fetchone()
                con.commit()
                return dict(row) if row else None
            finally:
                con.close()
        return await asyncio.to_thread(_run)

    async def executemany(self, sql: str, seq: Iterable[Iterable[Any]]):
        seq = [tuple(x) for x in seq]
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await self._pg_prepare(conn)
                    await conn.executemany(_pg_placeholders(sql), seq)
            return
        def _run():
            con = sqlite3.connect(self.sqlite_path)
            try:
                con.executemany(sql, seq)
                con.commit()
            finally:
                con.close()
        await asyncio.to_thread(_run)

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await self._pg_prepare(conn)
                    rows = await conn.fetch(_pg_placeholders(sql), *tuple(params))
                    return [dict(r) for r in rows]
        def _run():
            con = sqlite3.connect(self.sqlite_path)
            con.row_factory = sqlite3.Row
            try:
                return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]
            finally:
                con.close()
        return await asyncio.to_thread(_run)

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None


def _pg_placeholders(sql: str) -> str:
    """Translate qmark placeholders to asyncpg $N while preserving SQL syntax.

    Question marks inside quoted strings, identifiers, comments, and dollar-quoted
    PostgreSQL blocks are left untouched, as are JSONB operators ?, ?| and ?&.
    """
    out=[]; i=0; n=0; state="code"; dollar_tag=None
    while i < len(sql):
        ch=sql[i]; nxt=sql[i+1] if i+1 < len(sql) else ""
        if state == "code":
            if ch == "'": state="single"; out.append(ch); i+=1; continue
            if ch == '"': state="double"; out.append(ch); i+=1; continue
            if ch == '-' and nxt == '-': state="line"; out.extend([ch,nxt]); i+=2; continue
            if ch == '/' and nxt == '*': state="block"; out.extend([ch,nxt]); i+=2; continue
            if ch == '$':
                j=i+1
                while j < len(sql) and (sql[j].isalnum() or sql[j]=='_'): j+=1
                if j < len(sql) and sql[j] == '$':
                    dollar_tag=sql[i:j+1]; state="dollar"; out.append(dollar_tag); i=j+1; continue
            if ch == '?':
                # Preserve PostgreSQL JSONB operators ? ?| ?&. Qmark placeholders
                # in this codebase are followed by punctuation/whitespace, not |/&.
                if nxt in {'|','&'}:
                    out.append(ch); i+=1; continue
                n+=1; out.append(f"${n}"); i+=1; continue
            out.append(ch); i+=1; continue
        if state == "single":
            out.append(ch)
            if ch == "'":
                if nxt == "'": out.append(nxt); i+=2; continue
                state="code"
            i+=1; continue
        if state == "double":
            out.append(ch)
            if ch == '"':
                if nxt == '"': out.append(nxt); i+=2; continue
                state="code"
            i+=1; continue
        if state == "line":
            out.append(ch); i+=1
            if ch == '\n': state="code"
            continue
        if state == "block":
            out.append(ch)
            if ch == '*' and nxt == '/': out.append(nxt); i+=2; state="code"; continue
            i+=1; continue
        if state == "dollar":
            if dollar_tag and sql.startswith(dollar_tag, i):
                out.append(dollar_tag); i+=len(dollar_tag); state="code"; dollar_tag=None
            else:
                out.append(ch); i+=1
    return "".join(out)


db = Database(settings.database_url, settings.database_password_secret)
# Audit writes use an independent restricted PostgreSQL identity. SQLite tests
# share the same database object so the portable test suite remains simple.
audit_db = (
    Database(settings.audit_database_url, settings.audit_database_password_secret)
    if settings.audit_database_url != settings.database_url or db.is_postgres
    else db
)

"""Short-lived schema migration/bootstrap entrypoint.

This module runs in a separate container that receives the database-admin secret.
The API container never receives that credential and cannot perform DDL.
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import asyncpg


def read_secret(name: str) -> str:
    path = Path('/run/secrets') / name
    if not path.is_file():
        raise RuntimeError(f'missing migration secret: {path}')
    return path.read_text().strip()


async def main():
    host = os.getenv('POSTGRES_HOST', 'postgres')
    db = os.getenv('POSTGRES_DB', 'aurelian')
    user = os.getenv('POSTGRES_ADMIN_USER', 'aurelian_admin')
    password = read_secret('postgres_admin_password')
    conn = await asyncpg.connect(host=host, database=db, user=user, password=password, statement_cache_size=0)
    try:
        sql = Path('/srv/postgres/schema.sql').read_text()
        await conn.execute(sql)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

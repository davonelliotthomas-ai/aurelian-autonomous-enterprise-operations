import os, uuid
os.environ.setdefault("APP_ENV","test")
os.environ.setdefault("PUBLIC_DEMO","true")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN","test-internal-token-generated-for-pytest-only")
import pytest_asyncio
from app.database import db
from app.main import seed

@pytest_asyncio.fixture(autouse=True)
async def isolated_db(tmp_path):
    path=tmp_path/f"aurelian-{uuid.uuid4().hex}.db"
    db.url=f"sqlite:///{path}"; db.sqlite_path=str(path); db.pg_pool=None
    await db.connect(); await seed()
    yield
    await db.close()

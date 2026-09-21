"""baseline tenant-scoped schema
Revision ID: 0001
"""
from alembic import op
from pathlib import Path
revision='0001'; down_revision=None; branch_labels=None; depends_on=None
def upgrade():
 sql=Path(__file__).resolve().parents[2].joinpath('app/schema.sql').read_text()
 for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
  stmt=stmt.replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
  op.execute(stmt)
def downgrade():
 for t in ['compensations','audit_events','approvals','workflow_checkpoints','tasks','documents','incidents','orders','customers','products','tenants']: op.execute(f'DROP TABLE IF EXISTS {t}')

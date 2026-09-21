"""v0.3.5.2 resilience/idempotency state.

Adds durable request/tool execution identity and crash-recovery metadata.
"""
from alembic import op
import sqlalchemy as sa

revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('tasks', sa.Column('idempotency_key', sa.Text(), nullable=True))
    op.create_index('idx_tasks_idempotency','tasks',['tenant_id','actor','idempotency_key'],unique=True)
    op.add_column('approvals', sa.Column('started_at', sa.Text(), nullable=True))
    op.add_column('compensations', sa.Column('execution_key', sa.Text(), nullable=True))
    op.create_table(
        'tool_executions',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('phase', sa.Text(), nullable=False),
        sa.Column('tool_name', sa.Text(), nullable=False),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('args_hash', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('output_json', sa.Text(), nullable=True),
        sa.Column('error_type', sa.Text(), nullable=True),
        sa.Column('started_at', sa.Text(), nullable=False),
        sa.Column('completed_at', sa.Text(), nullable=True),
        sa.UniqueConstraint('tenant_id','idempotency_key',name='uq_tool_exec_idempotency'),
    )
    op.create_index('idx_tool_exec_tenant','tool_executions',['tenant_id','status','started_at'])
    op.execute('ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE tool_executions FORCE ROW LEVEL SECURITY')
    op.execute("CREATE POLICY tenant_isolation ON tool_executions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON tool_executions TO aurelian_app')
    op.execute('GRANT USAGE, SELECT ON SEQUENCE tool_executions_id_seq TO aurelian_app')


def downgrade():
    op.drop_table('tool_executions')
    op.drop_column('compensations','execution_key')
    op.drop_column('approvals','started_at')
    op.drop_index('idx_tasks_idempotency',table_name='tasks')
    op.drop_column('tasks','idempotency_key')

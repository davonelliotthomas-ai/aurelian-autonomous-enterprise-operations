-- Aurelian v0.3.5.2 PostgreSQL schema.
-- Executed only by the short-lived migration/bootstrap identity.

CREATE TABLE IF NOT EXISTS tenants (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
 price DOUBLE PRECISION NOT NULL, stock INTEGER NOT NULL, reorder_point INTEGER NOT NULL, status TEXT NOT NULL,
 margin_pct DOUBLE PRECISION NOT NULL, demand_trend TEXT NOT NULL, UNIQUE(tenant_id, sku)
);
CREATE TABLE IF NOT EXISTS customers (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, customer_code TEXT NOT NULL, name TEXT NOT NULL,
 segment TEXT NOT NULL, lifetime_value DOUBLE PRECISION NOT NULL, risk_score INTEGER NOT NULL, status TEXT NOT NULL,
 UNIQUE(tenant_id, customer_code)
);
CREATE TABLE IF NOT EXISTS orders (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, order_code TEXT NOT NULL, customer_code TEXT NOT NULL,
 sku TEXT NOT NULL, quantity INTEGER NOT NULL, total DOUBLE PRECISION NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(tenant_id, order_code)
);
CREATE TABLE IF NOT EXISTS incidents (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, title TEXT NOT NULL, severity TEXT NOT NULL,
 status TEXT NOT NULL, owner TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
 environment TEXT NOT NULL DEFAULT 'production', service TEXT NOT NULL DEFAULT 'general', trust_level TEXT NOT NULL DEFAULT 'trusted',
 updated_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, request TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL,
 status TEXT NOT NULL, workflow_state TEXT NOT NULL, result_json TEXT, idempotency_key TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_checkpoints (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, task_id BIGINT NOT NULL, node TEXT NOT NULL, attempt INTEGER NOT NULL,
 state_json TEXT NOT NULL, latency_ms DOUBLE PRECISION NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, task_id BIGINT NOT NULL, tool_name TEXT NOT NULL,
 args_json TEXT NOT NULL, actor TEXT NOT NULL, requester_role TEXT NOT NULL, approval_tier TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT NOT NULL, reviewed_by TEXT, review_note TEXT, mfa_verified INTEGER DEFAULT 0,
 created_at TEXT NOT NULL, reviewed_at TEXT, started_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, actor TEXT NOT NULL, event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL, signature TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compensations (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, task_id BIGINT NOT NULL, tool_name TEXT NOT NULL,
 compensation_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'available', execution_key TEXT, created_at TEXT NOT NULL
);


-- Incremental compatibility for existing v0.3.5/v0.3.5.1 volumes.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS started_at TEXT;
ALTER TABLE compensations ADD COLUMN IF NOT EXISTS execution_key TEXT;
CREATE TABLE IF NOT EXISTS tool_executions (
 id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, task_id BIGINT NOT NULL, phase TEXT NOT NULL,
 tool_name TEXT NOT NULL, idempotency_key TEXT NOT NULL, args_hash TEXT NOT NULL, status TEXT NOT NULL,
 output_json TEXT, error_type TEXT, started_at TEXT NOT NULL, completed_at TEXT, UNIQUE(tenant_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency ON tasks(tenant_id, actor, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_tool_exec_tenant ON tool_executions(tenant_id, status, started_at);
CREATE INDEX IF NOT EXISTS idx_docs_tenant ON documents(tenant_id, environment, service);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id, id);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant ON approvals(tenant_id, status);

DO $do$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['products','customers','orders','incidents','documents','tasks','workflow_checkpoints','approvals','audit_events','compensations','tool_executions']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
      t
    );
  END LOOP;
END
$do$;

CREATE OR REPLACE FUNCTION aurelian_prevent_audit_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$$;
DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION aurelian_prevent_audit_mutation();

-- Runtime roles never own schema objects and never receive DDL privileges.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aurelian_app, aurelian_audit_writer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aurelian_app, aurelian_audit_writer;
GRANT USAGE ON SCHEMA public TO aurelian_app, aurelian_audit_writer;

GRANT SELECT, INSERT, UPDATE ON tenants TO aurelian_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON products, customers, orders, incidents, documents, tasks, workflow_checkpoints, approvals, compensations, tool_executions TO aurelian_app;
GRANT SELECT ON audit_events TO aurelian_app;
GRANT SELECT, INSERT ON audit_events TO aurelian_audit_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aurelian_app;
GRANT USAGE, SELECT ON SEQUENCE audit_events_id_seq TO aurelian_audit_writer;

REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON audit_events FROM aurelian_app, aurelian_audit_writer;
REVOKE CREATE ON SCHEMA public FROM aurelian_app, aurelian_audit_writer;

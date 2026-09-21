CREATE TABLE IF NOT EXISTS tenants (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
 price REAL NOT NULL, stock INTEGER NOT NULL, reorder_point INTEGER NOT NULL, status TEXT NOT NULL,
 margin_pct REAL NOT NULL, demand_trend TEXT NOT NULL, UNIQUE(tenant_id, sku)
);
CREATE TABLE IF NOT EXISTS customers (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, customer_code TEXT NOT NULL, name TEXT NOT NULL,
 segment TEXT NOT NULL, lifetime_value REAL NOT NULL, risk_score INTEGER NOT NULL, status TEXT NOT NULL,
 UNIQUE(tenant_id, customer_code)
);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, order_code TEXT NOT NULL, customer_code TEXT NOT NULL,
 sku TEXT NOT NULL, quantity INTEGER NOT NULL, total REAL NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(tenant_id, order_code)
);
CREATE TABLE IF NOT EXISTS incidents (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, title TEXT NOT NULL, severity TEXT NOT NULL,
 status TEXT NOT NULL, owner TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
 environment TEXT NOT NULL DEFAULT 'production', service TEXT NOT NULL DEFAULT 'general', trust_level TEXT NOT NULL DEFAULT 'trusted',
 updated_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, request TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL,
 status TEXT NOT NULL, workflow_state TEXT NOT NULL, result_json TEXT, idempotency_key TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_checkpoints (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, task_id INTEGER NOT NULL, node TEXT NOT NULL, attempt INTEGER NOT NULL,
 state_json TEXT NOT NULL, latency_ms REAL NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, task_id INTEGER NOT NULL, tool_name TEXT NOT NULL,
 args_json TEXT NOT NULL, actor TEXT NOT NULL, requester_role TEXT NOT NULL, approval_tier TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT NOT NULL, reviewed_by TEXT, review_note TEXT, mfa_verified INTEGER DEFAULT 0,
 created_at TEXT NOT NULL, reviewed_at TEXT, started_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, actor TEXT NOT NULL, event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL, signature TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compensations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, task_id INTEGER NOT NULL, tool_name TEXT NOT NULL,
 compensation_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'available', execution_key TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_executions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, task_id INTEGER NOT NULL, phase TEXT NOT NULL,
 tool_name TEXT NOT NULL, idempotency_key TEXT NOT NULL, args_hash TEXT NOT NULL, status TEXT NOT NULL,
 output_json TEXT, error_type TEXT, started_at TEXT NOT NULL, completed_at TEXT, UNIQUE(tenant_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency ON tasks(tenant_id, actor, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_tool_exec_tenant ON tool_executions(tenant_id, status, started_at);
CREATE INDEX IF NOT EXISTS idx_docs_tenant ON documents(tenant_id, environment, service);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id, id);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant ON approvals(tenant_id, status);

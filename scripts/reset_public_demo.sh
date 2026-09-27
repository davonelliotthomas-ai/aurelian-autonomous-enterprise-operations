#!/usr/bin/env bash
set -euo pipefail

PROJECT="aurelian-v352-public-proof"

# Always attempt to leave the public interface running, even if a reset fails.
restore_services() {
    docker compose -p "$PROJECT" up -d api frontend >/dev/null 2>&1 || true
}
trap restore_services EXIT

echo "=== AURELIAN PUBLIC DEMO RESET ==="

echo "[1/5] Temporarily stopping public API/frontend..."
docker compose -p "$PROJECT" stop frontend api >/dev/null

echo "[2/5] Clearing mutable demo state and reseedable business state..."
docker compose -p "$PROJECT" exec -T postgres \
psql -U aurelian_admin -d aurelian -v ON_ERROR_STOP=1 -P pager=off <<'SQL'
BEGIN;

-- Ephemeral workflow / visitor state
DELETE FROM approvals
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM compensations
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM tool_executions
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM workflow_checkpoints
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM tasks
WHERE tenant_id IN ('meridian','northstar');

-- Intentionally preserved:
--   audit_events
--
-- The audit ledger is append-only by design.
-- Public-demo recovery must never bypass or weaken that invariant.

-- These are deterministically recreated by app.main.seed().
DELETE FROM orders
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM incidents
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM customers
WHERE tenant_id IN ('meridian','northstar');

DELETE FROM products
WHERE tenant_id IN ('meridian','northstar');

-- Intentionally preserved:
--   tenants
--   documents
--   Qdrant vectors

COMMIT;
SQL

echo "[3/5] Restarting API so existing seed() restores baseline..."
docker compose -p "$PROJECT" up -d api >/dev/null

echo "[4/5] Waiting for API health..."
for i in $(seq 1 30); do
    if docker compose -p "$PROJECT" ps api | grep -q '(healthy)'; then
        break
    fi
    sleep 1
done

if ! docker compose -p "$PROJECT" ps api | grep -q '(healthy)'; then
    echo "FAIL: API did not become healthy after reset" >&2
    exit 1
fi

docker compose -p "$PROJECT" up -d frontend >/dev/null

echo "[5/5] Verifying restored baseline..."

docker compose -p "$PROJECT" exec -T postgres \
psql -U aurelian_admin -d aurelian -P pager=off -c "
SELECT 'tenants' AS table_name, count(*) FROM tenants
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'customers', count(*) FROM customers
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'incidents', count(*) FROM incidents
UNION ALL SELECT 'documents', count(*) FROM documents
UNION ALL SELECT 'tasks', count(*) FROM tasks
UNION ALL SELECT 'approvals', count(*) FROM approvals
UNION ALL SELECT 'tool_executions', count(*) FROM tool_executions
UNION ALL SELECT 'compensations', count(*) FROM compensations
UNION ALL SELECT 'workflow_checkpoints', count(*) FROM workflow_checkpoints
UNION ALL SELECT 'audit_events', count(*) FROM audit_events
ORDER BY table_name;
"

echo "[verify] Enforcing expected reset state..."

docker compose -p "$PROJECT" exec -T postgres psql -U aurelian_admin -d aurelian -At -v ON_ERROR_STOP=1 <<'SQL' | grep -qx 'PASS'
WITH counts AS (
    SELECT
        (SELECT count(*) FROM tenants) AS tenants,
        (SELECT count(*) FROM products) AS products,
        (SELECT count(*) FROM customers) AS customers,
        (SELECT count(*) FROM orders) AS orders,
        (SELECT count(*) FROM incidents) AS incidents,
        (SELECT count(*) FROM documents) AS documents,
        (SELECT count(*) FROM tasks) AS tasks,
        (SELECT count(*) FROM approvals) AS approvals,
        (SELECT count(*) FROM tool_executions) AS executions,
        (SELECT count(*) FROM compensations) AS compensations,
        (SELECT count(*) FROM workflow_checkpoints) AS checkpoints
)
SELECT CASE
    WHEN tenants = 2
     AND products = 12
     AND customers = 6
     AND orders = 6
     AND incidents = 4
     AND documents = 10
     AND tasks = 0
     AND approvals = 0
     AND executions = 0
     AND compensations = 0
     AND checkpoints = 0
    THEN 'PASS'
    ELSE 'FAIL'
END
FROM counts;
SQL

echo
echo "=== RESET COMPLETE ==="
echo "Expected core baseline:"
echo "tenants=2 products=12 customers=6 orders=6 incidents=4 documents=10"
echo "Expected workflow state:"
echo "tasks=0 approvals=0 tool_executions=0 compensations=0 workflow_checkpoints=0"
echo "audit_events are intentionally preserved as an append-only ledger."

#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${BASE_URL:-http://localhost:8080}

echo '== Compose services =='
docker compose ps

echo '== Health =='
curl -fsS "$BASE_URL/health"; echo

echo '== Runtime application role =='
docker compose exec -T postgres psql -U aurelian_admin -d aurelian -c "SELECT rolname, rolsuper, rolbypassrls, has_schema_privilege(rolname,'public','CREATE') AS schema_create, has_table_privilege(rolname,'audit_events','INSERT') AS audit_insert, has_table_privilege(rolname,'audit_events','UPDATE') AS audit_update, has_table_privilege(rolname,'audit_events','DELETE') AS audit_delete, has_table_privilege(rolname,'audit_events','TRUNCATE') AS audit_truncate FROM pg_roles WHERE rolname='aurelian_app';"

echo '== Audit writer role =='
docker compose exec -T postgres psql -U aurelian_admin -d aurelian -c "SELECT rolname, rolsuper, rolbypassrls, has_table_privilege(rolname,'audit_events','SELECT') AS audit_select, has_table_privilege(rolname,'audit_events','INSERT') AS audit_insert, has_table_privilege(rolname,'audit_events','UPDATE') AS audit_update, has_table_privilege(rolname,'audit_events','DELETE') AS audit_delete, has_table_privilege(rolname,'audit_events','TRUNCATE') AS audit_truncate FROM pg_roles WHERE rolname='aurelian_audit_writer';"

echo '== PostgreSQL RLS direct canary =='

# First prove that Northstar rows actually exist. This prevents a vacuous PASS.
ADMIN_NORTHSTAR=$(docker compose exec -T postgres \
  psql -U aurelian_admin -d aurelian -At \
  -c "SELECT count(*) FROM products WHERE tenant_id='northstar';")

if [ "${ADMIN_NORTHSTAR:-0}" -le 0 ]; then
  echo 'FAIL: Northstar RLS canary rows do not exist'
  exit 1
fi

# Then connect as the real runtime application role, establish Meridian tenant
# context, and make an intentionally UNFILTERED cross-tenant query.
APP_NORTHSTAR=$(docker compose exec -T postgres sh -ec '
  export PGPASSWORD="$(cat /run/secrets/postgres_app_password)"
  psql -h 127.0.0.1 -U aurelian_app -d aurelian -At -v ON_ERROR_STOP=1 \
    -c "SELECT set_config('"'"'app.tenant_id'"'"','"'"'meridian'"'"',false);
        SELECT count(*) FROM products WHERE tenant_id='"'"'northstar'"'"';" \
    | tail -n1
')

if [ "$APP_NORTHSTAR" != "0" ]; then
  echo "FAIL: RLS exposed $APP_NORTHSTAR Northstar rows to Meridian"
  exit 1
fi

echo "PASS: admin sees $ADMIN_NORTHSTAR Northstar canary row(s); Meridian runtime role sees 0"

echo '== Runtime app cannot mutate audit ledger =='
if docker compose exec -T postgres sh -ec '
  export PGPASSWORD="$(cat /run/secrets/postgres_app_password)"
  psql -h 127.0.0.1 -U aurelian_app -d aurelian -v ON_ERROR_STOP=1 -c "BEGIN; SELECT set_config('"'"'app.tenant_id'"'"','"'"'meridian'"'"',true); UPDATE audit_events SET actor=actor WHERE false; COMMIT;"
' >/dev/null 2>&1; then
  echo 'FAIL: aurelian_app unexpectedly has audit UPDATE privilege'; exit 1
else
  echo 'PASS: aurelian_app audit UPDATE denied'
fi

echo '== Runtime container privilege posture =='
docker compose exec -T tool-runner sh -ec "grep -Eq '^CapEff:[[:space:]]+0000000000000000$' /proc/1/status && grep -Eq '^NoNewPrivs:[[:space:]]+1$' /proc/1/status"
docker compose exec -T planner sh -ec "grep -Eq '^CapEff:[[:space:]]+0000000000000000$' /proc/1/status && grep -Eq '^NoNewPrivs:[[:space:]]+1$' /proc/1/status"
echo 'PASS: tool-runner and planner have zero effective capabilities + no-new-privileges'

echo '== Tool-runner DB network isolation =='
docker compose exec -T tool-runner python3 - <<'PY'
import socket,sys
try:
    socket.getaddrinfo('postgres',5432)
except socket.gaierror:
    print('PASS: postgres DNS is not visible from tool-runner network')
    sys.exit(0)
print('FAIL: postgres resolved from tool-runner'); sys.exit(1)
PY

echo '== Planner DB network isolation =='
docker compose exec -T planner python3 - <<'PY'
import socket,sys
try:
    socket.getaddrinfo('postgres',5432)
except socket.gaierror:
    print('PASS: postgres DNS is not visible from planner network')
    sys.exit(0)
print('FAIL: postgres resolved from planner'); sys.exit(1)
PY

echo '== Frontend backend-network isolation =='
docker compose exec -T frontend sh -ec 'wget -qO- http://api:8000/health >/dev/null'
for target in 'postgres 5432' 'redis 6379' 'qdrant 6333' 'opa 8181'; do
  set -- $target
  if docker compose exec -T frontend sh -ec "nc -z -w 1 $1 $2 >/dev/null 2>&1"; then
    echo "FAIL: frontend reached $1:$2"; exit 1
  else
    echo "PASS: frontend cannot reach $1:$2"
  fi
done

echo '== Redis authentication =='
docker compose exec -T redis sh -ec 'redis-cli ping 2>&1 | grep -q NOAUTH'
docker compose exec -T redis sh -ec 'redis-cli -a "$(cat /run/secrets/redis_password)" ping 2>/dev/null | grep -q PONG'
echo 'PASS: Redis rejects unauthenticated clients and accepts secret-authenticated clients'

echo '== Qdrant authentication =='
docker compose exec -T api python3 - <<'PY'
import urllib.request, urllib.error
url='http://qdrant:6333/collections'
try:
    urllib.request.urlopen(url, timeout=3)
except urllib.error.HTTPError as e:
    if e.code not in (401,403):
        raise
else:
    raise SystemExit('FAIL: unauthenticated Qdrant request succeeded')
key=open('/run/secrets/qdrant_api_key').read().strip()
req=urllib.request.Request(url,headers={'api-key':key})
with urllib.request.urlopen(req,timeout=3) as r:
    assert r.status==200
print('PASS: Qdrant authentication enforced')
PY

echo '== Behavioral security checks =='
TOKEN=$(curl -fsS "$BASE_URL/api/auth/demo-token?role=executive&tenant_id=meridian&mfa=true" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/evals/run" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d,indent=2)); assert d["passed"]==d["total"]'

echo '== Concurrent approval CAS =='
OP_TOKEN=$(curl -fsS "$BASE_URL/api/auth/demo-token?role=operator&tenant_id=meridian&mfa=true" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
EX_TOKEN=$(curl -fsS "$BASE_URL/api/auth/demo-token?role=executive&tenant_id=meridian&mfa=true" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
KEY=verify-approval-$(date +%s%N)
REQ=$(curl -fsS -H "Authorization: Bearer $OP_TOKEN" -H "Idempotency-Key: $KEY" -H 'Content-Type: application/json' -d '{"request":"Change price AUR-101 to $997"}' "$BASE_URL/api/tasks")
AID=$(python3 - "$REQ" <<'PY'
import json,sys
r=json.loads(sys.argv[1]); assert r['status']=='pending_approval',r; print(r['approval_id'])
PY
)
TMP1=$(mktemp); TMP2=$(mktemp); C1=$(mktemp); C2=$(mktemp)
(curl -sS -o "$TMP1" -w '%{http_code}' -H "Authorization: Bearer $EX_TOKEN" -H 'Content-Type: application/json' -d '{"note":"concurrent-a"}' "$BASE_URL/api/approvals/$AID/approve" >"$C1") &
P1=$!
(curl -sS -o "$TMP2" -w '%{http_code}' -H "Authorization: Bearer $EX_TOKEN" -H 'Content-Type: application/json' -d '{"note":"concurrent-b"}' "$BASE_URL/api/approvals/$AID/approve" >"$C2") &
P2=$!
wait $P1; wait $P2
python3 - "$(cat "$C1")" "$(cat "$C2")" <<'PY'
import sys
codes=sorted(map(int,sys.argv[1:3])); assert codes==[200,409],codes
print('PASS: exactly one concurrent approval claimed execution')
PY
rm -f "$TMP1" "$TMP2" "$C1" "$C2"

echo '== OPA fail-closed =='
OP_TOKEN=$(curl -fsS "$BASE_URL/api/auth/demo-token?role=operator&tenant_id=meridian&mfa=true" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
docker compose pause opa >/dev/null
trap 'docker compose unpause opa >/dev/null 2>&1 || true' EXIT
RESULT=$(curl -fsS -H "Authorization: Bearer $OP_TOKEN" -H 'Content-Type: application/json' -H 'Idempotency-Key: verify-opa-fail-closed-0001' -d '{"request":"Change price AUR-101 to $1"}' "$BASE_URL/api/tasks")
python3 - "$RESULT" <<'PY'
import json,sys
r=json.loads(sys.argv[1])
assert r['status']=='blocked', r
print('PASS: OPA outage denied side-effect workflow')
PY
docker compose unpause opa >/dev/null
trap - EXIT

echo 'v0.3.5.2 runtime verification completed.'

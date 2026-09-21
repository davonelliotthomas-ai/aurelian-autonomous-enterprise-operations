# Verification Report — v0.3.5.2 Phase 2 Candidate

## Executed in this build environment

- Python compile across `app/`, `tool_runner/`, `planner_runner/`, `tests/`: **PASS**
- portable pytest regression suite: **36/36 PASS**
- frontend JavaScript `node --check`: **PASS**
- Docker Compose YAML parse with PyYAML: **PASS**
- static Phase 2 topology assertions: **PASS**
  - frontend uses only `edge + frontend_api` and is absent from backend `internal`;
  - API bridges `frontend_api`, `internal`, `tool_exec`, and `planner_exec`;
  - tool runner remains isolated to `tool_exec`;
  - planner remains isolated to `planner_exec`;
  - Redis `requirepass` is configured;
  - Qdrant API-key authentication is configured;
  - API mounts Redis/Qdrant client secrets but not the PostgreSQL admin secret.
- universal hardcoded demo JWT/audit/internal-token literals in executable Python source: **not present**.

## New Phase 2 controls

- durable `tool_executions` receipts with deterministic execution keys;
- side-effect tools are not automatically retried after ambiguous failures;
- ambiguous outcomes become `execution_unknown` / `recovery_required` rather than silent replay;
- startup reconciliation marks stale approvals, executions, compensations, and orphaned `CREATED` tasks for recovery;
- `POST /api/tasks` accepts actor-scoped `Idempotency-Key` values;
- compensation metadata is bound to the registered original-tool/compensation pair before rollback;
- prompt input is NFKC-normalized and zero-width characters are stripped before classification;
- configured guard-model failure or malformed output fails closed for side-effect policy by producing high input risk;
- demo token route exists only when `PUBLIC_DEMO=true`; production overlay forces it off and requires OIDC settings;
- frontend/backend Docker networks are separated;
- Redis and Qdrant authentication are configured;
- OIDC discovery/JWK clients are cached;
- SQLite is rejected outside explicit demo/test environments;
- local RAG fallback cache is bounded.

## Runtime integration configured, not executed here

This environment has no Docker daemon. Therefore **do not claim that v0.3.5.2 has passed live Docker/PostgreSQL/OPA validation yet**.

The repository now includes `scripts/verify_v352.sh` and a GitHub Actions `runtime-security-integration` job designed to run the exact Compose topology and verify:

1. clean service health;
2. application/audit PostgreSQL role restrictions;
3. direct PostgreSQL RLS visibility as `aurelian_app` without application-side tenant predicates;
4. runtime denial of audit mutation;
5. tool-runner and planner inability to resolve PostgreSQL;
6. frontend reachability to API but not PostgreSQL/Redis/Qdrant/OPA;
7. Redis unauthenticated rejection and secret-authenticated success;
8. Qdrant unauthenticated rejection and API-key-authenticated success;
9. all live `/api/evals/run` checks passing;
10. OPA outage causing a side-effect workflow to fail closed.

Bandit and `pip-audit` are configured in CI but are **not installed in this build environment**, so their results are not claimed here.

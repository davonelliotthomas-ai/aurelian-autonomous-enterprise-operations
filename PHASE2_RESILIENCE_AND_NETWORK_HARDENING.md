# v0.3.5.2 Phase 2 — Resilience and Network Hardening

This phase is the second implementation tranche derived from six independent adversarial reviews of the frozen v0.3.5 source.

## Implemented in Phase 2

### Durable execution / idempotency
- `tool_executions` stores deterministic execution identity, phase, tool, argument hash, state, output receipt, and completion/error metadata.
- New side-effect executions claim a durable receipt **before** invoking the tool.
- Side-effect tools are not automatically retried after ambiguous failures; the execution becomes `execution_unknown` and the task becomes `recovery_required`.
- A completed execution receipt can be reused to finish workflow state without re-running the tool.
- Rollback executions receive their own execution identity and compensation metadata is validated against the registered original-tool/compensation relationship.
- `POST /api/tasks` accepts `Idempotency-Key`, unique per tenant + actor.

### Crash detection / recovery queue
- Approval claims record `started_at`.
- Startup reconciliation detects stale `executing` approvals, tool executions and compensations.
- Stale `CREATED/running` tasks are marked `RECOVERY_REQUIRED` rather than silently replayed.
- `/api/recovery` exposes the current tenant's recovery queue to executive identities.

### Identity / secrets / guard path
- Universal working demo JWT, audit-signing and service-token literals were removed from executable source.
- Demo/test required secrets are generated randomly per process if not explicitly supplied.
- The demo-token route is registered only when `PUBLIC_DEMO=true`; secure default is false.
- `docker-compose.production.yml` forces `PUBLIC_DEMO=false` and requires OIDC settings.
- OIDC discovery/JWK clients are cached instead of recreated for every request.
- Untrusted input is Unicode-normalized and zero-width separators are removed before classification.
- A configured guard-model timeout/error or malformed response yields `high` risk / fail-closed classification for side-effect policy.

### Network / data-service hardening
- Frontend no longer joins the backend `internal` network; `frontend_api` is shared only by frontend and API.
- Redis requires a secret-managed password.
- Qdrant API-key authentication is enabled; the API reads its key from a mounted secret.
- Local RAG fallback cache is bounded and the Redis client is reused rather than recreated per operation.
- SQLite is rejected outside explicit `demo` / `test` environments.

### Automated evidence configured
- Portable test suite: **36/36 PASS** in this build environment.
- Runtime CI job now builds the real Compose topology and is designed to test PostgreSQL RLS, audit privileges, network reachability, runtime capabilities, Redis/Qdrant authentication, live evaluation checks, concurrent approval CAS, and OPA fail-closed behavior.

## Important claim boundary

The runtime Compose integration job and `scripts/verify_v352.sh` are **configured but were not executed in this build environment because no Docker daemon is available**. This version must not be described as live-validated until that job or the workstation run completes successfully.

## Remaining production hardening

- dedicated read-only audit verification identity rather than using the audit writer for verification reads;
- mTLS / workload identity between internal services;
- KMS/HSM or dedicated audit-signing service so compromise of the control plane cannot mint future valid audit events;
- external immutable audit anchoring if non-repudiation beyond the application trust boundary is required;
- automatic domain-specific reconciliation for `execution_unknown` events. Phase 2 deliberately chooses human-visible recovery over unsafe automatic replay;
- fully dialect-native SQL instead of the current safer qmark-to-asyncpg translation layer;
- Bandit and dependency-audit results must come from CI; they are not claimed from this local build.

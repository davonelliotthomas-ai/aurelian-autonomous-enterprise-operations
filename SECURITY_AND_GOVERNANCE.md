# Security & Governance — v0.3.5

## Scope

This artifact is a public technical demonstration of security architecture for autonomous operations. It demonstrates controls associated with zero-trust design, tenant isolation, human governance, policy enforcement, auditability and observability. It does **not** claim SOC 2, ISO 27001, FedRAMP, PCI DSS or any other certification.

## Trust model

The design assumes:
- user input, retrieved documents and model/planner output may be malicious or wrong;
- authenticated identity does not automatically imply authorization;
- prior authorization may become stale before execution;
- application compromise must not imply database-admin or audit-rewrite authority;
- an execution container may be compromised and must have a narrow blast radius;
- telemetry and audit evidence can itself become a data-leak channel if raw secrets/prompts are recorded.

## Identity and authorization

Protected APIs require a signed bearer token. The former unsigned demo-header role fallback has been removed.

Authorization is externalized through OPA when configured. If OPA is configured but unavailable, the application fails closed rather than silently treating a local fallback as permission.

High-risk actions require executive scope plus MFA. Approval is not sufficient on its own: the engine performs a fresh policy evaluation immediately before execution.

## Approval replay / TOCTOU controls

- approval records begin `pending`;
- a reviewer must satisfy current OPA policy, current scope and current MFA requirements;
- a compare-and-set update transitions exactly one reviewer from `pending` to `executing`;
- a second reviewer receives a conflict rather than executing the action twice;
- engine performs a second JIT policy check before invoking the tool;
- completed and failed executions are explicitly recorded.

`events.py` is telemetry-only SSE fanout; it is not a privileged job queue.

## Database duties

### `aurelian_admin`
- PostgreSQL bootstrap/migration identity;
- receives schema ownership/DDL ability;
- used only by the short-lived migration service;
- credential is **not mounted into the API**.

### `aurelian_app`
- runtime business-data identity;
- `NOSUPERUSER`, `NOBYPASSRLS`, no schema `CREATE`;
- DML only on business tables;
- SELECT-only access to audit events.

### `aurelian_audit_writer`
- separate runtime identity used only by `app/audit.py`;
- `NOSUPERUSER`, `NOBYPASSRLS`;
- SELECT+INSERT on `audit_events` only;
- no UPDATE/DELETE/TRUNCATE/TRIGGER/DDL privileges.

## Row-Level Security

Tenant tables use FORCE RLS policies based on `current_setting('app.tenant_id', true)`.

Every PostgreSQL data operation:
1. checks out a pooled connection;
2. opens an explicit transaction;
3. sets tenant context with `set_config(..., true)` (transaction-local / SET LOCAL semantics);
4. executes the query;
5. commits/rolls back;
6. pool reset executes `DISCARD ALL` before reuse.

This creates two independent state-cleanup boundaries.

## Audit integrity

Audit events use SHA-256 chaining plus HMAC-SHA256 signatures. Append operations acquire a tenant-scoped PostgreSQL advisory transaction lock before reading the previous hash, preventing concurrent writers from creating multiple competing chain heads.

The audit table is owned by the migration/admin identity; runtime application credentials cannot rewrite or truncate it.

## Tool-execution isolation

The tool runner:
- exposes only explicit allow-listed operations;
- has no generic shell/Python/HTTP execution endpoint;
- runs as UID/GID 10001;
- uses a read-only filesystem;
- drops all Linux capabilities;
- enables `no-new-privileges`;
- uses `tmpfs` with `noexec,nosuid,nodev`;
- has PID, memory and CPU limits;
- attaches only to `tool_exec`, a dedicated internal Docker network shared with API and Jaeger;
- cannot resolve/reach PostgreSQL, OPA, Redis or Qdrant through Docker service networks.

## Planner / model boundary

Untrusted request planning occurs in a separate `aurelian-planner` container. It receives:
- no Docker secrets;
- no database connection;
- no tool-runner token;
- no public network route.

The current public demo planner is deterministic. A future live LLM adapter should replace the internals of this no-secret service rather than executing inside the secret-bearing control plane.

## RAG protections

- tenant/environment/service/trust metadata filtering;
- trusted/verified documents only enter eligible retrieval output;
- high-risk prompt-injection content is auto-quarantined to `untrusted` at ingestion;
- deterministic public-demo embeddings avoid external API-key dependencies;
- no retrieved document can directly invoke an arbitrary execution primitive.

## Secret lifecycle

Full Docker deployment uses Compose secret mounts under `/run/secrets`. Secrets are not supplied to the API/tool runner as ordinary environment variables.

The source also supports AWS Secrets Manager as an optional provider adapter.

Dynamic automatic rotation is not claimed in v0.3.5; that remains a future production concern.

## Tracing and data minimization

W3C Trace Context is propagated through browser/Nginx/API/downstream services. Spans record bounded operational metadata only and deliberately avoid raw authorization headers, prompts, document content and secret values.

Raw user requests remain in the task business record for the synthetic demo but are not duplicated into audit payloads or workflow-checkpoint telemetry. Audit records use request SHA-256 and length metadata.

## CI / verification

GitHub Actions defines:
- compile checks;
- pytest;
- Bandit SAST;
- `pip-audit` dependency scanning;
- committed-secret pattern checks;
- Docker Compose validation;
- SHA-256 executable/test-code artifact generation.

A passing CI pipeline is evidence of configured checks, not a security certification.

## v0.3.5.2 Phase 2 addendum — resilience and internal-service boundaries

The six-review remediation pass adds controls that are intentionally conservative around uncertain side effects:

- a durable `tool_executions` table records deterministic execution identity, arguments hash, state, output receipt, and completion/error metadata;
- a side-effecting tool with an ambiguous failure is **not automatically retried**; its execution becomes `execution_unknown` and the task becomes `recovery_required`;
- stale `executing` approvals, tool executions, compensations, and orphaned `CREATED` tasks are detected at startup and placed into a recovery queue rather than silently replayed;
- task creation supports actor-scoped `Idempotency-Key` semantics;
- rollback compensation is checked against a registered original-tool/compensation relationship before execution;
- Redis requires a secret-managed password and Qdrant requires an API key;
- the edge-facing frontend no longer joins the backend `internal` network; it shares only a dedicated `frontend_api` network with the control-plane API;
- SQLite is a demo/test-only fallback and is rejected in other application environments;
- configured external guard-model failures and malformed responses classify input as high risk, which causes medium/high side-effect policy to fail closed.

The build still treats mTLS between internal services, externally anchored audit signing/KMS, and full automated crash-recovery orchestration as production deployment hardening rather than completed controls. Runtime Docker/PostgreSQL/OPA verification remains required before claiming live validation for this version.

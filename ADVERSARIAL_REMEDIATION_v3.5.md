# v0.3.5 Adversarial Remediation Matrix

This document maps the seven findings from the external adversarial review to the actual v0.3.4 implementation and the v0.3.5 remediation. It deliberately distinguishes true defects from exploit assumptions that did not exist in the source.

## 1. Tool-runner container escape / blast radius — **HARDENED**

**Review concern:** arbitrary code running as root on a shared Docker network could pivot into PostgreSQL.

**v0.3.4 reality:** the runner already used a non-root user, `read_only`, `cap_drop: ALL`, and `no-new-privileges`, and exposed no arbitrary-code tool. However it did share the broad `internal` network with PostgreSQL/OPA.

**v0.3.5 remediation:**
- explicit UID/GID `10001:10001`;
- dedicated `tool_exec` network shared only by API, tool runner and Jaeger;
- PostgreSQL/OPA/Redis/Qdrant are not attached to `tool_exec`;
- no external egress (`internal: true`);
- `read_only`, `cap_drop: ALL`, `no-new-privileges`;
- PID, memory and CPU limits;
- `tmpfs` with `noexec,nosuid,nodev`;
- finite tool-name allowlist remains mandatory;
- adversarial test asserts no `python`/arbitrary-code endpoint and checks network topology.

## 2. RLS bleed through pooled PostgreSQL session state — **DEFENSE IN DEPTH ADDED**

**Review concern:** session tenant variables might survive pool reuse.

**v0.3.4 reality:** tenant state was already set with `set_config(..., true)` *inside the same explicit transaction*, which is PostgreSQL transaction-local state and is removed at COMMIT/ROLLBACK.

**v0.3.5 remediation:**
- preserves transaction-local tenant scoping;
- sets `statement_cache_size=0`;
- asyncpg pool reset executes `DISCARD ALL` before a connection is reused;
- live behavioral checks switch tenants across pooled queries and assert only the new tenant's rows are visible.

## 3. TOCTOU stale authorization — **REMEDIATED AT THE REAL EXECUTION BOUNDARY**

**Review concern:** an async event worker might execute an action after permissions are revoked.

**v0.3.4 reality:** `events.py` was SSE telemetry only; it never dequeued or executed privileged jobs. The real stale-decision risk existed between approval request creation and later approval execution.

**v0.3.5 remediation:**
- approval execution recomputes input risk;
- re-queries OPA immediately before side-effect execution;
- verifies current approval tier/scopes/MFA;
- OPA outage fails closed;
- atomic `UPDATE ... WHERE status='pending'` claims the approval, preventing replay/double execution;
- engine performs a second JIT-policy checkpoint immediately before the tool call;
- rollback requires executive+MFA and a new policy check.

## 4. Audit evidence controlled by application owner — **ARCHITECTURE CHANGED**

**Review concern:** a compromised app role could alter/truncate its own audit evidence.

**v0.3.5 remediation:**
- schema/DDL runs under a short-lived migration service using `aurelian_admin`;
- API does not receive the admin password;
- `aurelian_app` has no schema `CREATE` and no audit write privileges;
- `aurelian_audit_writer` receives only `SELECT + INSERT` on `audit_events`;
- both runtime roles are `NOSUPERUSER` + `NOBYPASSRLS`;
- audit table trigger rejects UPDATE/DELETE;
- TRUNCATE/TRIGGER/REFERENCES privileges explicitly revoked;
- audit appends use a tenant advisory lock to prevent concurrent chain forks.

## 5. RAG injection / in-process secret exposure — **BOUNDARY STRENGTHENED**

**Review concern:** a live LLM processing poisoned RAG context in the same secret-bearing process could exfiltrate process secrets through an HTTP tool.

**v0.3.4 reality:** this exact path did not exist: the demo used deterministic planning, no generic outbound HTTP tool, no arbitrary code endpoint, and untrusted RAG documents were excluded.

**v0.3.5 remediation:**
- request planning moved to a dedicated `aurelian-planner` container;
- planner receives no Docker secrets and no database access;
- planner network has no external egress;
- API/tool runner remain on internal-only networks;
- container secrets are mounted through `/run/secrets`, not normal process environment variables;
- high-risk injected documents are automatically downgraded to `untrusted` even if submitted as trusted;
- raw prompts are removed from audit/checkpoint telemetry.

## 6. Broken distributed trace propagation — **REMEDIATED**

W3C Trace Context now propagates through:

`browser → Nginx → FastAPI → planner/tool-runner → Jaeger`

Changes:
- browser emits standards-shaped `traceparent` headers;
- Nginx forwards `traceparent`/`tracestate`;
- FastAPI extracts parent context and returns `X-Aurelian-Trace-ID`;
- API injects active context into planner/tool-runner requests;
- both downstream services reconstruct parent context and emit their own spans;
- tool failures record error spans;
- SSE event payloads include trace IDs when available.

## 7. Weak PASS conditions — **TEST MODEL EXPANDED**

The suite now uses side-effect-aware assertions rather than equating an HTTP error code with safety.

Examples:
- malformed bearer token: expected 401 + task count unchanged + audit count unchanged + raw token absent from response;
- prompt injection: blocked + product price unchanged + task reaches terminal BLOCKED + marker absent from checkpoints/audit;
- unauthorized approval: expected 403 + price unchanged + approval remains pending;
- tool timeout: retries exhausted + task FAILED + business state unchanged;
- approval replay: second approval is 409 + exactly one `tool.executed` audit event;
- runner isolation and admin-secret absence are checked against Compose topology.

## Current local/static verification

- Python compile: PASS
- frontend JavaScript syntax: PASS
- Compose YAML structural assertions: PASS
- pytest: **20/20 PASS**

Full Docker runtime validation must be repeated on a Docker-capable workstation after upgrading from v0.3.4 because this ChatGPT execution sandbox cannot launch Docker.

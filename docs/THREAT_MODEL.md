# Threat Model — v0.3.5

| Threat | Primary control | Residual risk |
|---|---|---|
| Prompt injection attempts side effect | input classifier + OPA default deny + JIT recheck | novel injection patterns still require ongoing testing |
| Stale approval / role revocation | JIT OPA evaluation immediately before execution + atomic approval claim | external IAM revocation freshness depends on OIDC/OPA integration design |
| Approval replay | compare-and-set `pending → executing` | distributed retries must preserve idempotency at external side-effect target |
| Tool runner compromise | non-root, capabilities dropped, read-only FS, no-new-privileges, resource limits, dedicated no-egress network, allowlist | container/kernel vulnerabilities remain possible |
| Cross-tenant database exposure | FORCE RLS + transaction-local tenant setting + DISCARD ALL pool reset | SQL/schema changes must preserve RLS coverage |
| Runtime app compromises audit evidence | separate audit writer + admin-owned audit table + no runtime DDL + HMAC/hash chain | DB superuser compromise remains outside runtime trust boundary |
| Concurrent audit chain fork | tenant advisory transaction lock | cross-region/multi-database replication would need stronger ordering strategy |
| RAG poisoning | ingestion quarantine + trust metadata + retrieval filters | malicious trusted-author content still needs review/evaluation |
| Secret exfiltration through model | no-secret planner + no generic HTTP/code tool + no-egress internal networks + Docker secret mounts | control-plane RCE could still access runtime secrets it legitimately requires |
| Sensitive telemetry leakage | prompt hashes/lengths in checkpoints/audit; bounded span attributes | business task table retains raw synthetic request text by design |
| Trace correlation loss | W3C `traceparent` propagation API→planner/tool runner | third-party SaaS integrations would need equivalent propagation support |
| Denial of service in runner | timeout + PID/memory/CPU limits + retries | host-wide resource starvation still requires infrastructure quotas |

## Explicit non-claims

- Docker/container isolation is not a proof against kernel escape.
- Hash chaining is not an immutable external ledger.
- RLS is only as complete as schema/policy coverage.
- The deterministic planner is not a frontier LLM evaluation.
- The demo is not a compliance certification or formal penetration test.

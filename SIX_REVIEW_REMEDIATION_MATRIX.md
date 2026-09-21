# Aurelian v0.3.5.2 — Six-Review Consolidated Remediation Matrix

Source baseline: frozen **v0.3.5** reviewed six times without source changes (three initial adversarial passes + three DeepSeek passes).

Status legend: **DONE** = patched in v0.3.5.2 working tree; **NEXT** = accepted for next implementation tranche; **VALIDATE** = requires live PostgreSQL/Compose evidence; **DID** = defense-in-depth; **REJECTED** = reviewer premise did not match the implementation.

| ID | Consolidated issue | Review convergence | Decision | Status |
|---|---|---:|---|---|
| R-01 | Compensation side effect executes before atomic claim | Multiple independent reviews | Claim `available -> executing` before tool execution; finalize `used`; failure -> `execution_failed` | **DONE** |
| R-02 | Rollback hardcodes input risk to `low` | Multiple independent reviews | Reclassify originating task request and pass actual risk into JIT policy | **DONE** |
| R-03 | Rollback/side-effect idempotency and crash ambiguity | Multiple reviews | Durable `tool_executions` receipt + deterministic execution key; ambiguous side-effect failure becomes `execution_unknown` rather than automatic replay | **DONE** |
| R-04 | Approval may remain `executing` after process death | DeepSeek Pass #2 | `started_at` + startup stale-state reconciliation; interrupted executions become `recovery_required` | **DONE** |
| R-05 | Task can be orphaned between INSERT and workflow start | DeepSeek Pass #2 | Startup reconciler marks stale `CREATED/running` tasks `RECOVERY_REQUIRED`; no blind replay | **DONE** |
| R-06 | No request idempotency key | DeepSeek Pass #2 | Optional `Idempotency-Key`, unique per tenant+actor, returns existing task/result on retry | **DONE** |
| R-07 | Policy audit fingerprint can misattribute OPA decisions | Original review #3 | Carry actual decision policy source + fingerprint; hash mounted Rego artifact | **DONE** |
| R-08 | Pipe-delimited audit signing envelope is ambiguous | Original review #3 | Canonical JSON envelope with explicit versioned fields | **DONE** |
| R-09 | Audit chain-head query lacks explicit tenant predicate | Original review #1 | Add explicit `tenant_id` predicate in addition to FORCE RLS | **DONE** |
| R-10 | 32-bit `hashtext()` advisory lock namespace | Original review #2 | Use 64-bit `hashtextextended(...,0)` advisory key | **DONE** |
| R-11 | `verify_chain()` reads through business DB facade | DeepSeek #1/#3 | Route verification through audit DB facade; future dedicated read-only audit role | **DONE** (facade); reader role **NEXT** |
| R-12 | Automatic `RETURNING id` SQL mutation | Original review #1 | Explicit `insert_returning_id()` API | **DONE** |
| R-13 | Naive `? -> $N` SQL translation | Original review #3 + DeepSeek #1 | Parser now preserves literals/comments/dollar blocks/JSON operators; longer-term dialect-native SQL | **DONE** |
| R-14 | Deny endpoint weaker than approval tier | Original review #1 + DeepSeek #3 | Require tier-appropriate approval scope to deny | **DONE** |
| R-15 | VERIFY state is unconditional `True` | DeepSeek #1 | Perform tool-specific output-schema verification; fail workflow on invalid output | **DONE** |
| R-16 | Planner/checkpoint data-minimization gaps | DeepSeek #1 | Hash parsed business identifiers/amounts in plan checkpoints | **DONE** |
| R-17 | Guard-model failure/invalid response can degrade classification | Original review #2/#3 | Unicode normalization, strict LOW/MEDIUM/HIGH parsing, configured guard failures classify high risk | **DONE** |
| R-18 | Public demo token issuer can mint executive+MFA identities | DeepSeek #1 | Demo route is registered only when `PUBLIC_DEMO=true`; production overlay forces false and requires OIDC | **DONE** |
| R-19 | Static universal demo secrets in source | DeepSeek #1/#3 | Removed universal fallback literals; demo/test required secrets are random per process unless explicitly supplied | **DONE** |
| R-20 | Frontend is attached to backend `internal` network | DeepSeek #3 | Dedicated `frontend_api` network; frontend no longer joins PostgreSQL/Redis/Qdrant/OPA network | **DONE** |
| R-21 | Redis has no authentication | DeepSeek #1/#3 | Secret-managed `requirepass`; API reads password from Docker secret; runtime check added | **DONE / VALIDATE** |
| R-22 | Qdrant has no authentication | DeepSeek #3 | Qdrant API key enabled; API client sends `api-key` from mounted secret; runtime negative test added | **DONE / VALIDATE** |
| R-23 | Tool-runner token string comparison not constant-time | DeepSeek #3 | Use `hmac.compare_digest()` | **DONE** |
| R-24 | OIDC JWKS client recreated per request | DeepSeek #3 | Persistent cached `PyJWKClient` + discovery URI cache | **DONE** |
| R-25 | SQLite permitted as fallback outside explicit test/demo | Multiple reviews | `Database.connect()` rejects SQLite unless `APP_ENV` is demo/test | **DONE** |
| R-26 | Pytest suite is SQLite-only and cannot prove PostgreSQL boundaries | All review families | Added runtime Compose CI job exercising PostgreSQL/RLS/OPA exact topology | **CONFIGURED / VALIDATE** |
| R-27 | Compose network tests are static YAML assertions only | DeepSeek #1/#3 | Runtime verification now tests frontend/tool/planner network reachability plus Redis/Qdrant auth | **CONFIGURED / VALIDATE** |
| R-28 | RLS eval relies on SKU prefixes/data presence | Original review #3 | Eval now checks returned `tenant_id`; runtime script performs direct unfiltered RLS query as `aurelian_app` | **CONFIGURED / VALIDATE** |
| R-29 | In-memory SQLite audit lock is process-local | Original review #1 | SQLite is explicitly restricted to demo/test and is not a production persistence mode | **DONE (scope guard)** |
| R-30 | Local RAG fallback cache is unbounded | DeepSeek #1 | Bounded TTL/LRU fallback + persistent Redis client pool | **DONE** |
| R-31 | Redis/Qdrant/internal service mTLS absent | DeepSeek #3 | Production-only DID; service auth/segmentation first, mTLS deployment profile later | **DID** |
| R-32 | Alembic config contains stale demo DB credentials | DeepSeek #3 | Replace with non-working placeholder | **DONE** |
| R-33 | Package version mismatch + duplicate config field | DeepSeek #1/#3 | Single current version and remove duplicate field | **DONE** |

## Findings explicitly not accepted as demonstrated vulnerabilities

- **v3.5 PostgreSQL audit chain cross-tenant contamination via unqualified chain-head SELECT:** RLS is FORCE-enabled and the audit writer is NOBYPASSRLS; explicit tenant predicate was still added for clarity and defense in depth.
- **Request-body word `returning` breaks SQL mutation:** bound values are not interpolated into SQL text; the heuristic was still removed.
- **`REQUIRE_SECRET_FILES=true` falls through to tool-runner hardcoded token:** source raises before fallback; static defaults remain scheduled for removal.
- **OPA `environment` omission currently bypasses approval:** current risk tiers already require approval for medium/high regardless; consistency improvement remains optional.
- **Same-Compose-file placement alone implies sandbox escape:** topology and effective network membership, not file co-location, determine reachability.

## v0.3.5.2 Phase 2 verification

- Python compile checks: required.
- Portable pytest regression suite: **36/36 PASS** after Phase 2 patches.
- Phase 2 tests add durable execution replay, ambiguous side-effect failure handling, poisoned-compensation rejection, task idempotency, frontend network segmentation, internal-service authentication configuration, production demo-token disablement, and universal-secret-literal checks.
- Live PostgreSQL/OPA/Compose evidence: **not yet claimed** for v0.3.5.2 in this build environment. Runtime CI/workstation verification is configured but must actually run.

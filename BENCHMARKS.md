# Demo Benchmarks & Acceptance Criteria — v0.3.5

The project intentionally avoids invented business-outcome claims. Public metrics must come from an attached benchmark run or client-approved case study.

## Measured signals
- workflow-node and distributed-span latency;
- retry count and terminal state;
- approval replay/conflict behavior;
- signed audit-chain validity;
- tenant/RLS behavioral checks;
- runtime DB-role privilege checks;
- k6 HTTP/load profile.

## Acceptance criteria before public showcase
- 100% passing automated tests;
- no cross-tenant data exposure under RLS/pool reuse checks;
- runtime app role has no superuser/bypass-RLS/schema-create/audit-write authority;
- audit writer has SELECT+INSERT only;
- high-risk side effects require executive+MFA and JIT reauthorization;
- an approval can execute at most once;
- prompt-injection attempt produces no business-state mutation;
- tool timeout terminates safely after bounded retries;
- raw prompt markers are absent from audit/checkpoint telemetry;
- audit chain remains verifiable;
- planner/tool-runner are unreachable from public networks and cannot reach PostgreSQL through Docker service networks;
- Jaeger correlates browser/API/downstream spans.

Do not publish MTTR, throughput, cost-reduction or reliability percentages until a real benchmark run is preserved as evidence.

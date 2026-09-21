# Aurelian Autonomous Enterprise Operations

Designed and built a production-shaped technical demonstration of governed autonomous enterprise operations and zero-trust agent execution.

The system combines signed identity, OPA policy, risk-tiered human approvals, just-in-time reauthorization, tenant-isolated PostgreSQL/RLS, a no-secret planning boundary, isolated allow-listed tool execution, hybrid retrieval, W3C-distributed tracing, and cryptographically verifiable audit evidence.

A core demonstration shows an autonomous workflow proposing a high-risk business change while external controls prevent execution until a currently authorized executive+MFA identity approves it. The approval is then re-evaluated immediately before execution and protected against replay.

Additional adversarial scenarios test prompt injection, tenant isolation, tool failures, audit tampering, authorization failure, and container/network trust boundaries.

**Stack:** Python · FastAPI · PostgreSQL/RLS · Redis · Qdrant · OPA/Rego · OpenTelemetry/Jaeger · Docker · Nginx · SSE · signed JWT/OIDC adapter · HITL governance

All company/customer/order data is synthetic. This is a technical demonstration, not a claim of client production deployment or compliance certification.

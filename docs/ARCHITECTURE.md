# Architecture — Aurelian Autonomous Enterprise Operations v0.3.5

## Container topology

```mermaid
flowchart TB
  Browser -->|traceparent + bearer| Frontend[Nginx / Frontend]
  Frontend --> API[Control Plane API]

  API -->|planner_exec only| Planner[No-Secret Planner]
  API -->|tool_exec only| Runner[Allow-Listed Tool Runner]
  API -->|internal| OPA[Open Policy Agent]
  API -->|internal| PG[(PostgreSQL)]
  API -->|internal| Redis[(Redis)]
  API -->|internal| Qdrant[(Qdrant)]

  Migrator[Short-Lived Migration Service] -->|admin DB identity| PG
  AuditWriter[aurelian_audit_writer] --> PG

  API --> Jaeger[Jaeger / OTLP]
  Planner --> Jaeger
  Runner --> Jaeger
```

## Network topology

- `edge`: frontend + Jaeger localhost UI path
- `internal` (`internal: true`): API, PostgreSQL, Redis, Qdrant, OPA, migration service, Jaeger
- `tool_exec` (`internal: true`): API, tool runner, Jaeger only
- `planner_exec` (`internal: true`): API, planner, Jaeger only

The tool runner and planner therefore have no Docker network path to PostgreSQL and no route to the public Internet.

## Data-plane transaction boundary

Each runtime PostgreSQL operation opens an explicit transaction and sets `app.tenant_id` transaction-locally. `DISCARD ALL` runs on pool reset before connection reuse.

## Control-plane execution

```mermaid
stateDiagram-v2
  [*] --> INPUT_GUARD
  INPUT_GUARD --> PLAN
  PLAN --> POLICY
  POLICY --> BLOCKED: deny
  POLICY --> WAIT_APPROVAL: governed write
  POLICY --> JIT_POLICY: immediate low-risk
  WAIT_APPROVAL --> JIT_POLICY: signed reviewer + atomic claim
  JIT_POLICY --> BLOCKED: current policy denies
  JIT_POLICY --> EXECUTE: current policy authorizes
  EXECUTE --> EXECUTE_RETRY: bounded failure
  EXECUTE_RETRY --> EXECUTE
  EXECUTE_RETRY --> FAILED: retry budget exhausted
  EXECUTE --> VERIFY
  VERIFY --> COMPLETE
```

## Observability topology

W3C Trace Context flows from the browser into the API. The API injects active context into planner/tool-runner calls. Downstream services extract that context and create child spans, allowing a single Jaeger trace to correlate user request → planning → control plane → isolated execution.

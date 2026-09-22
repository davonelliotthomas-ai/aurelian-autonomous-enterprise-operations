# Aurelian Autonomous Enterprise Operations

**A live-validated governed autonomous operations platform demonstrating policy-controlled execution, tenant isolation, approval workflows, audit integrity, observability, and isolated service execution.**

Built by **Davon Elliot Thomas** under **The Aurelian Group**.

---

## Overview

Aurelian Autonomous Enterprise Operations explores how AI-assisted and autonomous workflows can perform operational actions without giving an agent unrestricted control over production systems.

The platform places execution behind explicit technical controls including:

- policy evaluation
- signed identity
- role and scope authorization
- MFA-aware approval paths
- PostgreSQL Row Level Security
- isolated execution services
- audit-chain integrity
- prompt-injection controls
- failure handling
- distributed tracing
- runtime security verification

The engineering objective is not merely to make an autonomous system act.

It is to make its actions **governed, observable, attributable, and testable**.

---

## Architecture

![Aurelian Autonomous Enterprise Operations Architecture](docs/assets/aurelian-architecture.png)

*System architecture overview for Aurelian Autonomous Enterprise Operations v0.3.5.2.*


---

## Technology Stack

### Application
- Python
- FastAPI
- Pydantic
- asyncpg

### Data
- PostgreSQL
- Redis
- Qdrant

### Policy & Identity
- Open Policy Agent (OPA)
- JWT-based identity
- role / scope authorization
- MFA-aware approval paths

### Infrastructure
- Docker
- Docker Compose
- isolated service networks
- file-backed runtime secrets

### Observability
- OpenTelemetry
- Jaeger
- structured execution traces

### Assurance
- pytest
- Bandit SAST
- pip-audit
- GitHub Actions
- runtime integration verification

---

## Governed Execution Model

```text
Request
   ↓
Identity Verification
   ↓
Input / Injection Guard
   ↓
Planning
   ↓
Policy Evaluation
   ↓
Risk Classification
   ↓
Approval Gate
   ↓
Just-in-Time Authorization
   ↓
Isolated Tool Execution
   ↓
Verification
   ↓
Audit + Trace
```

Higher-risk operations require stronger authorization than read-only or lower-risk operations.

The platform also implements concurrency controls designed to prevent multiple approval requests from claiming the same execution.

---

## Security and Isolation

### PostgreSQL

The runtime application role is configured without superuser or RLS-bypass privileges.

```text
NOSUPERUSER
NOBYPASSRLS
```

The application role does not receive schema-creation privileges and cannot mutate the audit ledger.

PostgreSQL Row Level Security is used for tenant isolation.

Live runtime verification exercised this using cross-tenant canary records.

### Audit Writer

A separate audit-writer identity is limited to the privileges required for audit append operations and cannot update or delete existing audit records.

### Tool Execution

The tool runner uses a restricted container posture including:

- non-root execution
- dropped Linux capabilities
- `no-new-privileges`
- read-only filesystem controls
- bounded resources

The tool runner is also isolated from the PostgreSQL network.

### Network Segmentation

Runtime verification demonstrated that:

- the tool runner cannot resolve PostgreSQL
- the planner cannot resolve PostgreSQL
- the frontend cannot directly reach PostgreSQL
- the frontend cannot directly reach Redis
- the frontend cannot directly reach Qdrant
- the frontend cannot directly reach OPA

### Service Authentication

Redis and Qdrant require authenticated access.

Runtime credentials are not committed to this public repository.

GitHub Actions generates temporary secrets for runtime CI and destroys them with the runner.

---

## Fail-Closed Behavior

Security-sensitive paths are designed to fail closed.

Example:

```text
OPA available
→ policy decision evaluated
→ permit or deny

OPA unavailable
→ side-effect workflow denied
```

The sandbox worker also terminates if required resource limits cannot be established rather than continuing execution without those controls.

---

## Testing and Validation

The current public repository passes its GitHub Actions pipeline.

Current checks include:

```text
✓ Python compilation
✓ 36 automated tests
✓ Bandit static security analysis
✓ dependency vulnerability audit
✓ secret-pattern checks
✓ Docker Compose validation
✓ runtime security integration
```

The runtime CI lane exercises the actual container topology rather than relying exclusively on mocked or SQLite-based behavior.

---

## Live Validation

A frozen engineering build of **v0.3.5.2** was executed and validated in a Docker Desktop + WSL2 environment.

Observed validation included:

- clean Docker bootstrap
- database migration completion
- PostgreSQL role separation
- PostgreSQL RLS isolation
- audit mutation denial
- container privilege checks
- network segmentation
- Redis authentication
- Qdrant authentication
- live OPA policy decisions
- concurrent approval CAS behavior
- OPA outage fail-closed behavior

Validation evidence is preserved under:

```text
runtime-evidence/
```

The evidence demonstrates behavior observed in the tested environment.

It is **not a claim of formal third-party security certification or proof against every possible vulnerability**.

---

## Runtime Evidence

The following screenshots are direct evidence from the running v0.3.5.2 system and its current CI pipeline.

### Operational Interface

![Actual Aurelian runtime interface](docs/assets/proof/runtime-ui.png)

*Actual Aurelian interface from the running system.*

### Docker Runtime and Security Controls

![Actual Aurelian Docker runtime](docs/assets/proof/docker-runtime.png)

*Containerized v0.3.5.2 runtime and security-validation evidence from Docker Desktop + WSL2.*

### Automated Runtime Verification

![Aurelian runtime verification](docs/assets/proof/runtime-verification.png)

*Completed v0.3.5.2 runtime verification, including concurrency and fail-closed policy behavior.*

### GitHub Actions CI

![Aurelian GitHub Actions CI](docs/assets/proof/github-ci.png)

*Public repository CI completing successfully after testing, security scanning, Compose validation, and runtime integration checks.*

### Distributed Trace — v0.3.5.2

![Aurelian Jaeger distributed trace](docs/assets/proof/jaeger-trace.png)

*Actual Jaeger/OpenTelemetry trace from a governed workflow execution, showing nine spans across the Aurelian control plane and planner service, including input guard, planning, policy evaluation, just-in-time policy, execution, and verification stages.*

These screenshots document observed behavior in the tested environments. They are not third-party certification or proof that the system is free from every possible vulnerability.

---

## Adversarial Review

The architecture went through multiple adversarial review and remediation passes covering areas such as:

- compensation race conditions
- tenant isolation
- policy provenance
- audit-chain construction
- prompt-injection handling
- secret management
- network segmentation
- database privileges
- concurrency
- CI assurance quality

Review findings resulted in implementation and architecture changes before the validated build was frozen.

---

## Repository Status

```text
Public source repository        ✓
GitHub Actions CI               ✓
Automated test suite            ✓
Static security analysis        ✓
Dependency vulnerability scan   ✓
Runtime integration tests       ✓
Local live validation           ✓
Public internet deployment      In progress
```

---

## Project Focus

This project demonstrates work relevant to:

- applied AI engineering
- agentic systems
- backend engineering
- secure workflow execution
- business automation
- systems integration
- internal tools
- AI platform engineering
- technical architecture

---

## Author

**Davon Elliot Thomas**

**The Aurelian Group**

Focused on AI systems, software engineering, automation, secure autonomous workflows, and advanced technical problem-solving.

---

## Technical Claim Boundary

The current demonstration uses deterministic and controlled components for portions of planning and execution.

It should not be interpreted as claiming that a paid external LLM autonomously drives every workflow.

The project demonstrates the surrounding engineering required to make autonomous operations governable, observable, and testable.

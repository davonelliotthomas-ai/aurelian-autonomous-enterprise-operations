# AURELIAN SIGNAL ENGINE — Building Data Integrity Before Building APIs

*By Davon Elliot Thomas | The Aurelian Group*

**Project 01 / 06: Python Data Engineering**

Every dependable API and analytics platform starts with a less glamorous question: can the underlying data be trusted?

I built the first entry in The Aurelian Group's engineering demonstration series around that question. **Aurelian Signal Engine** is a compact Python data processor that ingests synthetic business events in JSON or CSV format, validates their contents, normalizes amounts and timestamps, resolves duplicates, and produces a transparent analytical report.

The goal was to isolate fundamental engineering decisions before introducing a network service or cloud database.

## Five decisions that shaped the architecture

**1. Exact currency representation.** The engine uses Python's Decimal for parsing and converts supported monetary values to integer cents. It rejects floats, negative amounts, nonfinite values, and fractional cents rather than silently accepting ambiguous money.

**2. Immutable normalized records.** Frozen dataclasses provide a clear internal event contract. Tags are converted into tuples to avoid accidental mutation of nested state—an important distinction when reasoning about Python object references and shallow copies.

**3. Explicit record identity.** Deduplication uses (source, external_id) as a composite key. The newest timezone-normalized event wins; a tie preserves the first record. This keeps the result predictable.

**4. Observable data quality.** Invalid rows enter a quarantine log with their input row number and a reason. The valid dataset is still processed, but the number of rejected inputs is never hidden.

**5. One Python core, multiple interfaces.** The same business logic runs from a local CLI and in a browser using Pyodide. Format adapters feed a shared normalizer rather than duplicating business rules.

## What the demo shows

An eight-row fictional dataset produces six accepted unique records, one resolved duplicate, one quarantined invalid row, and a final value of $3,379.44. The report includes category totals and deterministic record ordering.

I wrote 21 automated tests covering currency edge cases, timezones, immutable state, duplicate policy, invalid input, empty datasets, and JSON/CSV equivalence.

The live demonstration runs Python in the browser and is hosted as a static site. It is a technical portfolio project, not a claim of enterprise production deployment. There is no server-side database, and the sample data is synthetic.

## Why this matters beyond Python

This engine establishes the data-contract foundation for subsequent Aurelian projects:

- SQL modeling, transactions, and concurrency.
- FastAPI request handling, Pydantic validation, and asynchronous application design.
- Backend authorization, error handling, and automated testing.
- Checkpointed ETL processing and Azure Data Factory orchestration.

My central principle: **reliable systems emerge from explicit invariants, intentional failure handling, and testable boundaries—not from the number of frameworks in a stack.**

The source code, tests, and interactive demonstration are available for technical review.

**Explore the project:**

- [Run the live Aurelian Signal Engine](https://davonelliotthomas-ai.github.io/aurelian-autonomous-enterprise-operations/)
- [Review the complete Python source and tests on GitHub](https://github.com/davonelliotthomas-ai/aurelian-autonomous-enterprise-operations/tree/aurelian-signal-engine/aurelian-signal-engine)

**Suggested LinkedIn Featured labels:**

- Live Demo: Aurelian Signal Engine — Python Data Quality Lab
- GitHub: Aurelian Signal Engine — 21-Test Python Engineering Project

**Technical scope:** This is a self-contained Python data-engineering demonstration, not an Azure deployment, FastAPI implementation, customer system, or production service.

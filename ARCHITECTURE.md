# Architecture and design review — Project 01

## System boundary

The source of truth is engine.py. The CLI calls it using the local Python runtime. The browser loads the same engine in Pyodide, invokes analyze_json() or analyze_csv(), and renders the resulting JSON report.

The browser downloads the Python runtime from a public CDN. The sample and user-supplied event records are processed locally in the tab; the app has no analytics endpoint, database, application-server POST request, login, or persistence. The JavaScript fallback is **labelled as a preview** and is not a substitute for Python tests.

## Processing topology

Raw JSON/CSV → parse → normalize/validate → quarantine bad rows → choose newest event by (source, external_id) → rank and aggregate → JSON report → dashboard.

## Why this decomposition?

- amount_to_cents has one responsibility: exact monetary conversion.
- normalize_event has one responsibility: producing one safe, immutable event.
- analyze_records owns quality controls, record-identity resolution, ranking, and aggregation.
- analyze_json and analyze_csv are format adapters that share business logic.
- cli.py and the website are delivery interfaces, not places to duplicate Python business rules.

## Critical invariants

1. Amounts are nonnegative, finite, have at most two decimal places, and are represented internally as integer cents.
2. Every normalized event has a timezone-aware UTC timestamp.
3. Tags are a tuple, with repeated tags removed in insertion order.
4. The engine never intentionally mutates caller-owned input records.
5. Identity is unique for (source, external_id); a newer revision wins. Equal timestamps retain the first observed version.
6. Bad records produce a row-indexed quality report without stopping valid processing.
7. Sorting is deterministic: amount descending, then external ID, then source.
8. The report is reproducible from the same input.

## Performance and tradeoffs

- Validation and deduplication are expected O(n) over n rows due to hash-map lookups.
- Sorting u unique accepted rows costs O(u log u).
- Memory is O(u + r) for unique accepted rows and r errors, plus input parsing overhead.
- iter_valid_events demonstrates lazy iteration, but analyze_records intentionally materializes a dictionary for sorting and deduplication. This is not an unbounded-memory streaming system.
- Composite keys prevent cross-source ID collisions, assuming source identifiers are reliable.
- A later timestamp alone does not prove a record is trustworthy; production ingestion must authenticate its source.
- Frozen dataclasses prevent ordinary field reassignment, but are not a security boundary. Nested data is made immutable using tuple tags.
- The monetary cap is a demonstration constraint. Real financial ledgers also need currency, taxation, audited rounding rules, and domain-specific controls.
- Python CSV input uses csv.DictReader. The JavaScript fallback parser is intentionally simpler and should not be trusted for full quoted-field CSV correctness.
- The demo has no persistence, no storage guarantees, and no cross-user consistency claims.
- Pyodide imposes an initial download and requires a third-party CDN. When unavailable the site visibly labels the alternative preview.

## Security model

The project processes fictional records. Browser input is untrusted and might contain malicious text, so output fields are HTML-escaped before rendering. Errors are rendered as text. Python never evals user input, loads untrusted modules, or sends records to an application server.

## Testing plan

The 21 unittest cases cover decimal exactness, bad monetary values, frozen event behavior, UTC conversion, naive datetime rejection, tag validation, generator iteration, composite-key identity, newest/equal-time decisions, quarantines, deterministic ordering, empty input, and JSON/CSV sample equivalence.

## Production evolution

- Project 02 introduces relational schema, SQL constraints, transactions, and concurrency.
- Project 03 serves the engine behind typed FastAPI endpoints using Pydantic request and response models.
- Project 04 adds authorization, user isolation, observability, and robust failure-handling.
- Project 05 adds checkpointed ETL runs, retries, and idempotency.
- Project 06 models cloud ingestion with Azure Data Factory pipelines, connection services, execution configuration, and monitoring.

These boundaries keep the claims precise and make the progression explainable.

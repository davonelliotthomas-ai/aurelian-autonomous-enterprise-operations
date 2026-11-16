# AURELIAN — Signal Engine

**Project 01 / 06 · Python Data Engineering**

An original engineering demonstration by **The Aurelian Group**. It validates, normalizes, deduplicates, and analyzes fictional business-event records. The Python core runs locally and in a browser using Pyodide (CPython compiled to WebAssembly).

> All records are invented. This is a technical demonstration, not a customer deployment or production platform. It uses no backend database, cloud resources, or hosted Python API.

## What it does

1. Ingests JSON or CSV business events.
2. Validates identifiers, categories, monetary amounts, ISO-8601 timestamps, and tags.
3. Converts decimal currency to **integer cents** and timezone-aware timestamps to **UTC**.
4. Uses immutable @dataclass(frozen=True, slots=True) records with tuple tags.
5. Deduplicates by composite (source, external_id) keys, retaining the newest timestamp; equal timestamps preserve the first record.
6. Quarantines invalid records with row-specific reasons instead of silently dropping them.
7. Aggregates category totals and returns a deterministic, ranked report.
8. Executes in standard-library Python; no Python dependencies are needed.

## Quick start (Windows PowerShell)

Open a terminal in this project directory:

~~~powershell
py --version
py cli.py data/sample.json
py cli.py data/sample.csv --output report.json
py -m unittest discover -s tests -v
~~~

On Linux/macOS, replace py with python3. The suite includes **21 tests** for timezones, money safety, deduplication, invalid records, deterministic ordering, and JSON/CSV equivalence.

## Try the interactive website

The dist/ directory contains the website. It uses the **same engine.py** as the local CLI and executes it inside the browser using Pyodide. All example data is synthetic.

If the Python CDN is inaccessible, the UI explicitly identifies a **JavaScript preview mode**; it does not mislabel the fallback as Python.

To preview locally:

~~~powershell
py -m http.server 8000 --directory dist
~~~

Visit http://localhost:8000. Serve over HTTP to allow source files to load.

## Repository layout

~~~text
engine.py                   Pure Python data engine
cli.py                      Command-line entry point
data/sample.json            Fictional business events
data/sample.csv             The same events as CSV
tests/test_engine.py        21 automated unit tests
dist/index.html             Interactive Aurelian experience
dist/styles.css             Responsive blue-and-white design
dist/app.js                 Browser runtime and visualization
dist/walkthrough.html       Browser-readable teaching article
docs/ENGINEERING_WALKTHROUGH.md  15-minute who/what/when/where/why/how guide
docs/ARCHITECTURE.md        Decisions, limitations, next steps
docs/LINKEDIN_ARTICLE.md    LinkedIn publication-ready technical post
screenshots/                Visual documentation
~~~

The copies in dist/ are refreshed from the root code during packaging. The root Python files are authoritative.

## Included sample result

| Metric | Result |
| --- | ---: |
| Input rows | 8 |
| Accepted unique records | 6 |
| Duplicate keys resolved | 1 |
| Invalid rows quarantined | 1 |
| Total amount | $3,379.44 |
| Distinct categories | 3 |

The revised billing / INV-1002 replaces an earlier event because its timestamp is newer. A three-decimal amount is quarantined.

## Demonstration runbook

1. Visit the website and wait for **CPython / WebAssembly ready** (or note the honest fallback).
2. Run the JSON sample and explain counts, records, categories, and quality log.
3. Select **CSV**, run the same dataset, and compare results.
4. Change one amount to 12.999; observe the validation failure.
5. Inspect engine.py in Source Explorer.
6. Explain Decimal, frozen dataclasses, composite deduplication keys, deterministic ordering, and quarantine.
7. Run the unit tests locally and show the actual result.

## Skills demonstrated

- **Python:** functions, type annotations, dataclasses, immutability, Decimal, dictionaries, sets, tuples, lists, generators, exceptions, deterministic sorting.
- **Data engineering:** parsing, normalization, record identity, deduplication, quality logging, aggregation, equivalence across formats.
- **Testing:** unittest, boundary conditions, failure paths, invariants, regression coverage.
- **Presentation layer:** semantic HTML, responsive CSS, vanilla JavaScript, accessible controls, Pyodide runtime.

## Future project boundaries

SQL persistence, FastAPI request handling, service authorization, multi-user processing, and Azure/ADF are deliberately **out of scope for Project 01**. They belong to Projects 02–06.

## Documentation

- [Technical architecture](docs/ARCHITECTURE.md)
- [15-minute explanatory walkthrough](docs/ENGINEERING_WALKTHROUGH.md)
- [LinkedIn article](docs/LINKEDIN_ARTICLE.md)

© 2026 The Aurelian Group. Project materials are supplied as a portfolio demonstration.

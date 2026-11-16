# Aurelian Signal Engine — the 15-minute architectural walkthrough

## Project 01 of 06 · Python Data Engineering

**Speaker:** Davon Elliot Thomas, The Aurelian Group

**Audience:** Software engineers, technical hiring managers, and curious non-engineers

**Purpose:** Explain who built this, what it does, when and where it runs, why its components exist, and how its engineering decisions work. The talk is written to be delivered in approximately 15 minutes at a deliberate pace. A shorter elevator pitch and a child-friendly explanation follow it.

## 00:00–01:15 — WHO: The Aurelian Group and the engineering objective

This project is called **Aurelian Signal Engine**, the first of six technical demonstrations in The Aurelian Group's Python, SQL, FastAPI, and cloud-data engineering series. The idea is straightforward: an enterprise system can only make reliable decisions when the information entering it has predictable meaning and quality.

For this first project, we wanted to isolate the core Python mechanics before adding a network API or database. A great deal of backend complexity comes from putting data validation, persistence, transformation, and request processing into one large function. Instead, we made a small engine whose behavior is easy to inspect, test, and extend.

All records used in this project are fictional. There is no live customer connection and no claim that this is already a production service. The value of the demonstration is that a reviewer can read its code, run its tests, change its input, and observe exactly what happens.

**For a child:** Think of Aurelian as a workshop making careful tools. This first tool checks a pile of information cards before anyone uses those cards to make a decision.

## 01:15–02:45 — WHAT: The business problem

Imagine a company receiving payment and activity events from several systems. One source identifies an event as INV-1002; another may use that same ID for something unrelated. Some timestamps use UTC while others contain local offsets. A payment amount might arrive as 249.99, a duplicate might be corrected later, and another record might contain an invalid amount such as 12.999.

Simply adding all rows would be wrong. You could double-count revisions, misinterpret time order, or accept more than two decimal places for currency. A reliable pipeline must establish explicit rules before aggregation.

The Signal Engine accepts a JSON array or CSV file. It validates each record, turns money into integer cents, converts timestamps to UTC, creates immutable event objects, resolves duplicates by a composite identifier, and produces a report. That report includes sorted accepted records, category totals, and a quarantine log explaining invalid rows.

Our example contains eight rows. Six unique valid events survive, one duplicate is resolved, and one invalid row is quarantined. The accepted total is $3,379.44.

**For a child:** Suppose eight receipts are placed on a desk. One is a newer version of an earlier receipt, and one has an impossible price. We keep the newest real receipt, put the broken one in a review pile, and add only the trustworthy receipts.

## 02:45–04:00 — WHEN and WHERE: The execution boundary

There are two legitimate execution paths for the same Python engine. Locally, a developer runs the command-line program using ordinary Python. In the public demonstration, the browser downloads Pyodide, a WebAssembly-based Python runtime, and executes the engine.py source directly in the visitor's browser.

This design makes the demo inexpensive to host. The website consists of HTML, CSS, JavaScript, and Python source files served as static assets. There is no dedicated Python application server and no database. The user-supplied input stays in the browser during analysis, with no application endpoint receiving those records.

There is a deliberate limitation here. The browser needs a CDN to load the Python runtime. If the runtime is unavailable, the page identifies a JavaScript preview fallback clearly. We never label a JavaScript result as execution of the actual Python engine.

In production, a future FastAPI project would provide a service boundary, authentication, database durability, background ingestion, and operational metrics. Those responsibilities are intentionally outside this first project.

**For a child:** The calculator runs on your own desk, rather than mailing your cards to a distant building. The website delivers the calculator, then your browser does the work.

## 04:00–05:30 — HOW, stage one: Parsing and validating

The first engineering choice is to distinguish the input format from the core data-processing rules. JSON and CSV have different parsing requirements, but they should not require two independent implementations of business validation.

The JSON adapter decodes a JSON array and passes the rows into a shared processing function. The CSV adapter uses Python's standard csv.DictReader, converts pipe-separated tag text into a list, and passes the resulting records to the same function.

The normalizer enforces nonempty source, external ID, and category fields. It checks that tags are structured as a list or tuple and that each tag is nonempty text. It rejects a timestamp that lacks a timezone, because comparisons between local and global times are unreliable without a stated offset.

The design separates “what is an event?” from “how did the event arrive?” An engineer can later introduce a database adapter, an HTTP adapter, or a queue consumer without rewriting the normalization rules.

**For a child:** We accept information written on two kinds of paper, but we always use the same checklist to decide whether the information is valid.

## 05:30–07:00 — HOW, stage two: Exact amounts and normalized time

Currency is a classic trap. Python floating-point numbers represent many decimal fractions approximately, because the underlying representation uses binary. For instance, 0.1 plus 0.2 does not have an exact binary representation equal to decimal 0.3.

The engine deliberately rejects float inputs for money, accepts decimal text, and parses it using Decimal. It rejects negative, nonfinite, and more-than-two-decimal-place values. Then it converts the exact value to an integer number of cents.

Once a record says 249.99, internal calculations use 24999 cents. Summing integers preserves the intended accounting quantity. The user interface formats cents back into a currency display only at the final presentation stage.

Time requires similar discipline. Python datetime.fromisoformat parses the timestamp, then astimezone(timezone.utc) converts it to UTC. A timestamp with an offset of -05:00 is translated into the corresponding UTC instant. This lets the system decide which duplicate is truly newer, even when events originate in different time zones.

We also impose a maximum amount as an explicit domain constraint. In a real financial system we would additionally define currency codes, rounding rules, tax treatment, and audit requirements.

**For a child:** We count pennies instead of using fuzzy fractions of dollars. And we move every clock to the same time zone before deciding which event happened last.

## 07:00–08:30 — HOW, stage three: Immutable data and memory safety

Next is an important Python design choice: normalized events are represented as frozen dataclasses with slots. A dataclass gives us a named, typed structure instead of a loose dictionary with arbitrary fields. “Frozen” stops ordinary code from assigning new field values after the object is created. Slots reduce per-instance overhead and prevent unrelated dynamic attributes.

Tags are converted from a mutable input list into an immutable tuple. This matters because a frozen dataclass is not deeply immutable by itself: if a field pointed to a list, another component could still append to that list. By choosing immutable nested data, the project protects normalized state from common accidental mutations.

This directly applies the Python fundamentals of object references, shallow and deep copies, and mutable default arguments. The normalizer does not append to the caller's original list. Instead, it constructs a new tuple. The caller retains ownership of its input, and downstream code receives a stable, predictable event object.

Immutability is not security. It is a design tool to reduce accidental side effects and simplify reasoning. Authorization and untrusted-process isolation are separate problems for later projects.

**For a child:** After a receipt has passed inspection, we place it in a clear sealed sleeve. People can read it, but ordinary handling should not quietly change its contents.

## 08:30–10:00 — HOW, stage four: Record identity and duplicate resolution

The engine uses a Python dictionary as an index of the latest accepted event for each identity. That identity is a tuple containing source and external ID. This is a composite key.

Why not use external ID alone? Different upstream systems can issue the same identifier without referring to the same real-world event. The source provides a namespace and reduces accidental collision.

For each validated event, the engine checks whether its key is already present. If not, it inserts the record. If a matching key exists, it counts a duplicate and compares timestamps. The event with the later UTC timestamp wins. If timestamps match exactly, the earlier input row remains the winner. That tie-break rule is important: the outcome is deterministic, not dependent on unspecified iteration behavior.

Dictionary lookups are expected constant time on average, so the scan is expected O(n) for n input rows. After resolving duplicates, we sort the unique records by amount descending, then external ID, then source. Sorting takes O(u log u), where u is the number of unique accepted records.

This is an in-memory demonstration. Large datasets would require chunking, external sorting, or database-backed deduplication rather than assuming unlimited RAM.

**For a child:** Every receipt has a store name and receipt number. If we see the same store and number twice, we compare dates and keep the newest one. Two different stores are allowed to reuse the same number.

## 10:00–11:30 — HOW, stage five: Quarantine, totals, and output

Real datasets contain invalid records. Our engine avoids two extremes: silently accepting bad values, and throwing away the entire batch because one row is malformed.

Each row is validated inside a controlled try/except boundary. If it fails, the engine records the row number and the reason and moves on. Accepted records remain available for analysis. At the end, the system returns an explicit summary of input rows, unique accepted events, duplicate keys encountered, and quarantined records.

This is a deliberate choice that suits exploratory ingestion, but it would need policy adjustments in a payment settlement pipeline. Some domains require an all-or-nothing transaction. Others allow partial acceptance while raising an alert. The correct choice depends on the business invariant, not a universal programming rule.

The engine aggregates amounts by category using integer-cent values. It sorts categories by total descending, and returns a JSON-serializable report. Input-to-output behavior is deterministic for the same input and rules.

**For a child:** A broken receipt goes into a clearly labelled tray with an explanation. We still finish counting the good receipts, and we tell everyone exactly how many were accepted or rejected.

## 11:30–12:45 — WHY: Testing and engineering confidence

A green screen or attractive dashboard is not evidence of correctness. We wrote 21 automated unittest cases against the Python engine. The tests cover ordinary output and cases where the software should refuse a value.

Important examples include exact decimal conversion, rejection of negative or nonfinite amounts, rejection of fractional cents, timezone normalization, frozen-event behavior, duplicate ordering, tie breaking, bad-row quarantine, empty input, and equivalence of the JSON and CSV examples.

The unit tests run without network access or installation of third-party Python packages. The CLI, the business logic, and the browser presentation are separated, so failures can be investigated one layer at a time.

The tests do not prove the program is bug-free. They provide repeatable evidence for specific invariants, help prevent regressions, and make the engineering decisions auditable. Browser integration and accessibility testing are additional verification responsibilities.

**For a child:** We give the calculator easy receipts, tricky receipts, broken receipts, and duplicates. We check not just that it works when things are perfect, but that it behaves sensibly when things go wrong.

## 12:45–14:00 — THE ENGINEER'S REVIEW: Tradeoffs and future architecture

If I were discussing this with another engineer, I would call attention to four tradeoffs.

First, data is processed entirely in memory. That gives predictable speed for small datasets and zero infrastructure cost, but it limits maximum scale and offers no durable storage. Project 02 addresses relational modeling and transactions.

Second, quarantine is a domain-specific acceptance policy. It is appropriate for this analytics demonstration; for a regulated ledger we may need atomic commits, strict reconciliation, or a replay mechanism.

Third, a client-side demonstration minimizes backend cost and avoids transmitting sample records to an application server. It does not enforce trusted execution. Anyone can modify client-side code. For a production API, validation must happen on the trusted server, with authentication and authorization.

Fourth, the browser UI includes a fallback written in JavaScript. This keeps the visual demonstration usable if the external Python runtime CDN fails, but the fallback is a preview with a simpler CSV parser. The authoritative business rules and the 21 tests belong to Python, not to the fallback.

My next architectural step would be to put the processing functions behind typed FastAPI endpoints, validate requests with Pydantic, persist results in SQL under transaction boundaries, and build an incremental ingestion workflow with retry and idempotency rules. Azure Data Factory could then orchestrate cloud ingestion when the environment demands it.

**For a child:** This first machine is perfect for showing the idea on a desk. If thousands of people needed it at once, we would build a larger workshop with storage rooms, locks, schedules, and staff supervising the machines.

## 14:00–15:00 — THE CLOSE: What this project proves

The Aurelian Signal Engine is a deliberately small, transparent foundation for data-engineering systems. It proves that we can define data contracts, handle money and time precisely, reason about mutable state, model identifiers correctly, report validation failures, and verify those behaviors through automated tests.

It does not claim to be a hosted enterprise API, a durable financial ledger, or an Azure deployment. Those are future architectural layers, and separating them makes the engineering story more credible.

The business outcome is simple: **better input quality produces more reliable downstream decisions**. The engineering outcome is equally important: small components with explicit invariants are easier to test, debug, review, and extend.

My preferred closing line is: “We built this as a proof of engineering discipline: clearly defined inputs, visible failure paths, deterministic outputs, and tests that demonstrate the decisions encoded in the software.”

## One-minute elevator pitch

“Project 01 is an Aurelian-branded Python data-quality engine. It accepts sample JSON or CSV business events, validates every row, normalizes currency and timestamps, resolves duplicates by a composite business key, quarantines malformed records, and produces deterministic analytical summaries. I chose Decimal and integer cents for precise financial math, immutable dataclasses to prevent accidental state mutation, and a separation between format adapters and business logic so the engine can be reused behind a future FastAPI service. It has 21 automated Python tests and a zero-server-cost browser demonstration that runs the same Python source in WebAssembly. The next projects build outward into SQL, API security, incremental ETL, and Azure orchestration.”

## Explain it to a 10-year-old

“Pretend a business gives us a stack of receipts. Some are written as spreadsheets, others as lists. Some contain mistakes. Sometimes two receipts are actually the same transaction, but one has newer information. Aurelian built a sorting machine. It reads every receipt, makes sure the name and price are sensible, puts all times on one clock, and uses pennies so money adds up correctly. It keeps the latest receipt when it finds duplicates. If a receipt is wrong, it places it in a review basket and tells us why. Then it tells us how many good receipts we have and how much money each category contains. We tested the machine with 21 challenges so we can explain why we trust its results.”

## Engineer interview questions and answers

### Why Decimal instead of float?

Binary floating-point cannot represent all decimal fractions exactly. Decimal parses decimal strings exactly, then integer cents make permitted two-decimal amounts easy to aggregate without drift.

### Are frozen dataclasses deeply immutable?

No. Frozen prevents ordinary attribute reassignment. Nested mutable objects can still mutate. Using tuple tags closes that specific source of accidental change.

### Why a two-field deduplication key?

An upstream external ID may only be unique within its source. The tuple (source, external_id) preserves that namespace.

### What happens on equal timestamps?

The first accepted input record wins. The explicit tie-break policy yields a deterministic outcome for the same ordered input.

### Why quarantine instead of fail the whole batch?

This analytics demo prioritizes partial usable insight while preserving quality evidence. Financial settlement may instead require transactional all-or-nothing semantics.

### What is the complexity?

The dictionary scan is expected O(n). Ranking u accepted unique records costs O(u log u). Memory grows with unique events and errors.

### Is Pyodide a production backend?

No. It executes Python locally in the browser. It provides no trusted service boundary, remote storage, database transactions, or multi-user authorization.

### What can be made more robust next?

Explicit record schemas, source authentication, persistent SQL storage, idempotent ingestion, transaction boundaries, retry policy, metrics, tracing, and cloud orchestration.

## Rehearsal checklist

1. State the problem in one sentence.
2. Trace one raw JSON row through normalize_event().
3. Explain Decimal to integer cents and timezone normalization.
4. Explain the tuple key and latest-timestamp deduplication.
5. Explain why tags become a tuple.
6. Point to a quarantined bad row and its reason.
7. Run the 21 tests in a terminal.
8. Demonstrate both JSON and CSV input.
9. State what the site does **not** claim to do.
10. Bridge confidently to SQL, FastAPI, ETL, and Azure/ADF.

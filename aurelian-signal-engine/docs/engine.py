"""Aurelian Signal Engine — dependency-free, deterministic Python data processing.

The same module runs in ordinary CPython and in Pyodide (Python/WASM) in the
browser. No user data needs to be sent to an application server.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class Event:
    source: str
    external_id: str
    category: str
    amount_cents: int
    occurred_at: datetime
    tags: tuple[str, ...]


def required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def amount_to_cents(value: Any) -> int:
    """Convert an exact decimal amount to cents without binary float rounding."""
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError("amount must be a decimal string or integer")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("amount must be numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be finite and non-negative")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError("amount may contain at most two decimal places")
    if cents > 9_000_000_000_000_000:
        raise ValueError("amount exceeds supported range")
    return int(cents)


def normalize_event(raw: Mapping[str, Any]) -> Event:
    """Validate one record without modifying the caller's mapping or lists."""
    when = raw.get("occurred_at")
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("occurred_at must be ISO-8601") from exc
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise ValueError("occurred_at must include a timezone")

    raw_tags = raw.get("tags", [])
    if not isinstance(raw_tags, (list, tuple)):
        raise ValueError("tags must be a list")
    tags = tuple(dict.fromkeys(required_text(tag, "tag") for tag in raw_tags))

    return Event(
        source=required_text(raw.get("source"), "source"),
        external_id=required_text(raw.get("external_id"), "external_id"),
        category=required_text(raw.get("category"), "category"),
        amount_cents=amount_to_cents(raw.get("amount")),
        occurred_at=when.astimezone(timezone.utc),
        tags=tags,
    )


def iter_valid_events(rows: Iterable[Mapping[str, Any]]) -> Iterable[Event]:
    """Example generator: emits records lazily; fails on the first invalid row."""
    for row in rows:
        yield normalize_event(row)


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "source": event.source,
        "external_id": event.external_id,
        "category": event.category,
        "amount": f"{Decimal(event.amount_cents) / 100:.2f}",
        "amount_cents": event.amount_cents,
        "occurred_at": event.occurred_at.isoformat().replace("+00:00", "Z"),
        "tags": list(event.tags),
    }


def analyze_records(rows: Iterable[Any]) -> dict[str, Any]:
    """Normalize, quarantine invalid rows, and retain the newest event per key.

    Deduplication key: (source, external_id). For equal timestamps the first
    occurrence wins. Output ordering is deterministic. Totals use integer cents.
    """
    latest: dict[tuple[str, str], Event] = {}
    rejected: list[dict[str, Any]] = []
    seen = 0
    duplicates = 0

    for row_number, raw in enumerate(rows, start=1):
        seen += 1
        try:
            if not isinstance(raw, Mapping):
                raise ValueError("record must be a JSON object")
            event = normalize_event(raw)
        except (TypeError, ValueError) as exc:
            rejected.append({"row": row_number, "reason": str(exc)})
            continue

        key = (event.source, event.external_id)
        existing = latest.get(key)
        if existing is None:
            latest[key] = event
        else:
            duplicates += 1
            if event.occurred_at > existing.occurred_at:
                latest[key] = event

    ordered = sorted(latest.values(), key=lambda e: (-e.amount_cents, e.external_id, e.source))
    by_category: dict[str, dict[str, int]] = {}
    for event in ordered:
        entry = by_category.setdefault(event.category, {"count": 0, "amount_cents": 0})
        entry["count"] += 1
        entry["amount_cents"] += event.amount_cents

    categories = [
        {"category": name, "count": stats["count"], "amount_cents": stats["amount_cents"]}
        for name, stats in sorted(by_category.items(), key=lambda item: (-item[1]["amount_cents"], item[0]))
    ]
    total_cents = sum(event.amount_cents for event in ordered)
    return {
        "summary": {
            "input_rows": seen,
            "accepted_records": len(ordered),
            "rejected_rows": len(rejected),
            "duplicate_keys": duplicates,
            "total_amount_cents": total_cents,
            "total_amount": f"{Decimal(total_cents) / 100:.2f}",
            "categories": len(categories),
        },
        "categories": categories,
        "records": [event_to_dict(event) for event in ordered],
        "rejected": rejected,
    }


def analyze_json(input_text: str) -> str:
    parsed = json.loads(input_text)
    if not isinstance(parsed, list):
        raise ValueError("Input must be a JSON array of event objects")
    return json.dumps(analyze_records(parsed), separators=(",", ":"), ensure_ascii=False)


def analyze_csv(input_text: str) -> str:
    reader = csv.DictReader(io.StringIO(input_text))
    required = {"source", "external_id", "category", "amount", "occurred_at"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("CSV must contain source, external_id, category, amount, occurred_at")

    def rows() -> Iterable[dict[str, Any]]:
        for row in reader:
            record: dict[str, Any] = dict(row)
            record["tags"] = [tag.strip() for tag in (row.get("tags") or "").split("|") if tag.strip()]
            yield record

    return json.dumps(analyze_records(rows()), separators=(",", ":"), ensure_ascii=False)

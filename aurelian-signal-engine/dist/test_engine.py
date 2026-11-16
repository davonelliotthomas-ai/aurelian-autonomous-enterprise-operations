import csv
import io
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from engine import Event, amount_to_cents, analyze_csv, analyze_json, analyze_records, iter_valid_events, normalize_event


ROOT = Path(__file__).resolve().parents[1]
BASE = {"source": "billing", "external_id": "A-1", "category": "Services",
        "amount": "12.30", "occurred_at": "2026-11-12T10:00:00Z", "tags": ["new", "new"]}


class EngineTests(unittest.TestCase):
    def test_decimal_money_exact(self):
        self.assertEqual(amount_to_cents("12.30"), 1230)
        self.assertEqual(amount_to_cents(Decimal("0.01")), 1)

    def test_float_rejected(self):
        with self.assertRaisesRegex(ValueError, "decimal string"):
            amount_to_cents(1.25)

    def test_negative_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            amount_to_cents("-0.01")

    def test_fractional_cents_rejected(self):
        with self.assertRaisesRegex(ValueError, "two decimal"):
            amount_to_cents("1.234")

    def test_nonfinite_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                amount_to_cents(value)

    def test_normalization_and_immutability(self):
        raw = deepcopy(BASE)
        event = normalize_event(raw)
        self.assertIsInstance(event, Event)
        self.assertEqual(event.amount_cents, 1230)
        self.assertEqual(event.tags, ("new",))
        self.assertEqual(raw, BASE)
        self.assertEqual(event.occurred_at.tzinfo, timezone.utc)
        with self.assertRaises(Exception):
            event.amount_cents = 40

    def test_timezone_converted_to_utc(self):
        row = {**BASE, "occurred_at": "2026-11-11T05:00:00-05:00"}
        self.assertEqual(normalize_event(row).occurred_at, datetime(2026, 11, 11, 10, tzinfo=timezone.utc))

    def test_naive_datetime_rejected(self):
        row = {**BASE, "occurred_at": "2026-11-11T05:00:00"}
        with self.assertRaisesRegex(ValueError, "timezone"):
            normalize_event(row)

    def test_bad_tag_type_rejected(self):
        with self.assertRaisesRegex(ValueError, "tags must"):
            normalize_event({**BASE, "tags": "str"})

    def test_generator_lazy(self):
        rows = [BASE, {**BASE, "external_id": "A-2"}]
        iterator = iter(iter_valid_events(rows))
        self.assertEqual(next(iterator).external_id, "A-1")
        self.assertEqual(next(iterator).external_id, "A-2")
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_latest_duplicate_wins(self):
        older = BASE
        newer = {**BASE, "amount": "16.00", "occurred_at": "2026-11-13T10:00:00Z"}
        report = analyze_records([older, newer])
        self.assertEqual(report["summary"]["duplicate_keys"], 1)
        self.assertEqual(report["summary"]["accepted_records"], 1)
        self.assertEqual(report["summary"]["total_amount_cents"], 1600)

    def test_older_duplicate_cannot_revert(self):
        newer = {**BASE, "amount": "16.00", "occurred_at": "2026-11-13T10:00:00Z"}
        report = analyze_records([newer, BASE])
        self.assertEqual(report["records"][0]["amount"], "16.00")

    def test_equal_time_first_wins(self):
        report = analyze_records([BASE, {**BASE, "amount": "20.00"}])
        self.assertEqual(report["records"][0]["amount"], "12.30")

    def test_composite_key_prevents_cross_source_collision(self):
        report = analyze_records([BASE, {**BASE, "source": "other"}])
        self.assertEqual(report["summary"]["accepted_records"], 2)

    def test_invalid_row_quarantined(self):
        report = analyze_records([BASE, {**BASE, "amount": "oops"}, None])
        self.assertEqual(report["summary"]["rejected_rows"], 2)
        self.assertEqual(report["rejected"][0]["row"], 2)

    def test_invalid_json_top_level_rejected(self):
        with self.assertRaisesRegex(ValueError, "JSON array"):
            analyze_json('{"name":"single"}')

    def test_sample_json_report(self):
        sample = (ROOT / "data" / "sample.json").read_text(encoding="utf-8")
        report = json.loads(analyze_json(sample))
        self.assertEqual(report["summary"], {
            "input_rows": 8, "accepted_records": 6, "rejected_rows": 1,
            "duplicate_keys": 1, "total_amount_cents": 337944,
            "total_amount": "3379.44", "categories": 3,
        })

    def test_sample_csv_matches_json_report(self):
        json_report = json.loads(analyze_json((ROOT / "data" / "sample.json").read_text()))
        csv_report = json.loads(analyze_csv((ROOT / "data" / "sample.csv").read_text()))
        self.assertEqual(csv_report, json_report)

    def test_csv_required_columns(self):
        with self.assertRaisesRegex(ValueError, "CSV must contain"):
            analyze_csv("name,amount\nAurelian,10\n")

    def test_sorting_deterministic(self):
        rows = [{**BASE, "external_id": "B", "amount": "20.00"},
                {**BASE, "external_id": "A", "amount": "20.00"}]
        ids = [record["external_id"] for record in analyze_records(rows)["records"]]
        self.assertEqual(ids, ["A", "B"])

    def test_empty_input(self):
        self.assertEqual(json.loads(analyze_json("[]"))["summary"]["accepted_records"], 0)


if __name__ == "__main__":
    unittest.main()

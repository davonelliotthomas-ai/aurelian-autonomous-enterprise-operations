"""Run the Aurelian Signal Engine locally: python cli.py data/sample.json."""

import argparse
from pathlib import Path

from engine import analyze_csv, analyze_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Aurelian Signal Engine — local Python CLI")
    parser.add_argument("input", type=Path, help="Path to .json or .csv data file")
    parser.add_argument("--output", type=Path, help="Optional path for the JSON report")
    args = parser.parse_args()
    source = args.input.read_text(encoding="utf-8")
    report = analyze_csv(source) if args.input.suffix.lower() == ".csv" else analyze_json(source)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create deterministic, spreadsheet-safe P0 agent metrics rows."""

import argparse
import csv
import json
import sys


FIELDS = ("date", "repo", "issue", "result", "duration_seconds", "cost_micros", "reason")


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text


def normalized_row(record):
    if not isinstance(record, dict) or record.get("version") != 1:
        raise ValueError("invalid-agent-result")
    return {field: safe_cell(record.get(field)) for field in FIELDS}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    stream = sys.stdin if args.input == "-" else open(args.input, encoding="utf-8")
    try:
        records = json.load(stream)
        rows = [normalized_row(record) for record in records]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if stream is not sys.stdin:
            stream.close()
    writer = csv.DictWriter(sys.stdout, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(sorted(rows, key=lambda row: (row["date"], row["repo"], row["issue"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

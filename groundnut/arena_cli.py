"""Offline consumer for frozen Groundnut arena artifacts."""

from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys
from typing import Any, TypeVar

from .arena import ArenaPolicy, ArenaTask, Attack, Ruling, adjudicate


T = TypeVar("T")


def _read_jsonl(path: str | Path, record_type: type[T]) -> list[T]:
    allowed = {field.name for field in fields(record_type)}
    records = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: expected a JSON object")
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(
                f"{path}:{number}: unknown fields: {', '.join(sorted(unknown))}"
            )
        records.append(record_type(**value))
    return records


def _write_report(path: str | Path, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, sort_keys=True, indent=2) + "\n"
    Path(path).write_text(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, help="frozen policy JSON")
    parser.add_argument("--tasks", required=True, help="arena tasks JSONL")
    parser.add_argument("--attacks", required=True, help="arena attacks JSONL")
    parser.add_argument("--rulings", required=True, help="arena rulings JSONL")
    parser.add_argument("--out", required=True, help="report JSON destination")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        report = adjudicate(
            ArenaPolicy.from_json(args.policy),
            _read_jsonl(args.tasks, ArenaTask),
            _read_jsonl(args.attacks, Attack),
            _read_jsonl(args.rulings, Ruling),
        )
        _write_report(args.out, report.to_dict())
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"arena input error: {error}", file=sys.stderr)
        return 2
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

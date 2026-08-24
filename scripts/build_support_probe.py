"""Promote accepted pilot review rows into a frozen four-cell support probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_review import (  # noqa: E402
    PilotReviewManifest,
    build_pilot_probe_with_receipt,
    load_review_rows,
)
from groundnut.support_seeds import load_support_seeds  # noqa: E402
from prepare_support_pilot import _load_sources  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a support probe only from fully accepted review groups."
    )
    parser.add_argument("--reviewed-jsonl", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--seeds", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--build-attempt",
        required=True,
        type=int,
        help="1 for the first build of this manifest; increment on every rebuild",
    )
    args = parser.parse_args(argv)

    try:
        rows = load_review_rows(args.reviewed_jsonl)
        manifest = PilotReviewManifest.from_mapping(
            json.loads(args.manifest.read_text()), rows
        )
        seeds = load_support_seeds(args.seeds)
        sources = _load_sources(
            args.corpus_root, {row.candidate.source_id for row in rows}
        )
        probe, receipt = build_pilot_probe_with_receipt(
            manifest, seeds, sources, build_attempt=args.build_attempt
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"NOT READY: {error}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(case.canonical_payload(), sort_keys=True) + "\n"
            for case in sorted(probe.cases, key=lambda row: row.case_id)
        )
    )
    receipt_path = args.output.with_suffix(args.output.suffix + ".build.json")
    payload = {**receipt.to_dict(), "groups": probe.group_count, "cases": len(probe.cases)}
    receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({**payload, "output": str(args.output), "receipt": str(receipt_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

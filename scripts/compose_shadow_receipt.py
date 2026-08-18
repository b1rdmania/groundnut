#!/usr/bin/env python3
"""Compose an existing Groundnut run with optional experimental signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.shadow_composition import compose_shadow_receipt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--signal-envelope", type=Path)
    parser.add_argument("--signal-label", default="legacy_claim_excerpt_relatedness")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    run = json.loads(args.run.read_text())
    accounts = run["execution"]["run"]["evidence"]["accounts"]
    signals: dict[str, list[dict]] = {}
    if args.signal_envelope:
        envelope = json.loads(args.signal_envelope.read_text())
        for row in envelope["rows"]:
            signals.setdefault(row["case_id"], []).append(
                {
                    "label": args.signal_label,
                    "qualification": "unlabelled_unthresholded_observation",
                    "component_signal": row["component_signal"],
                }
            )

    receipt = compose_shadow_receipt(accounts, component_signals=signals)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "claim_count": receipt["claim_count"],
                "outcomes": receipt["outcomes"],
                "questions_present": receipt["questions_present"],
                "claims_with_experimental_signals": receipt[
                    "claims_with_experimental_signals"
                ],
                "sha256": receipt["sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

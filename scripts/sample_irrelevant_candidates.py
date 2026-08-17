"""Build a bounded, deterministic batch of cross-query review candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_seeds import (  # noqa: E402
    build_present_irrelevant_candidates,
    load_support_seeds,
    sample_present_irrelevant_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sample disjoint cross-query spans for human irrelevance review."
    )
    parser.add_argument("--seeds", required=True, type=Path)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--sampling-seed", required=True, type=int)
    parser.add_argument(
        "--max-span-envelope",
        type=int,
        help="Require both spans to fit inside this many source characters.",
    )
    parser.add_argument("--allow-repeated-sources", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    seeds = load_support_seeds(args.seeds)
    candidates = build_present_irrelevant_candidates(seeds)
    eligible = (
        candidates
        if args.max_span_envelope is None
        else tuple(
            candidate
            for candidate in candidates
            if max(candidate.original_end, candidate.distractor_end)
            - min(candidate.original_start, candidate.distractor_start)
            <= args.max_span_envelope
        )
    )
    selected = sample_present_irrelevant_candidates(
        candidates,
        count=args.count,
        sampling_seed=args.sampling_seed,
        unique_sources=not args.allow_repeated_sources,
        max_span_envelope=args.max_span_envelope,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payloads = [row.canonical_payload() for row in selected]
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in payloads)
    )
    batch_hash = hashlib.sha256(
        json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    print(
        json.dumps(
            {
                "schema": "groundnut-present-irrelevant-batch/v1",
                "available_candidates": len(candidates),
                "eligible_candidates": len(eligible),
                "selected_candidates": len(selected),
                "sampling_seed": args.sampling_seed,
                "max_span_envelope": args.max_span_envelope,
                "unique_sources": not args.allow_repeated_sources,
                "sha256": batch_hash,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

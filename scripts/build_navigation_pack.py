#!/usr/bin/env python3
"""Build a contamination-safe navigation pack from LegalBench-RAG seeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.navigation_cases import build_navigation_pack_from_seed_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--sampling-seed", type=int, default=991)
    parser.add_argument("--max-node-characters", type=int, default=3000)
    parser.add_argument("--allow-repeated-sources", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    result = build_navigation_pack_from_seed_file(
        args.seeds,
        args.corpus_root,
        count=args.count,
        sampling_seed=args.sampling_seed,
        unique_sources=not args.allow_repeated_sources,
        max_node_characters=args.max_node_characters,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_count": result["case_count"],
                "sha256": result["sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

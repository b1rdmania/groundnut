#!/usr/bin/env python3
"""Run answer-free full-injection and lexical structured-navigation baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.adapters.navigation import (  # noqa: E402
    FullInjectionNavigator,
    LexicalStructureNavigator,
)
from groundnut.navigation_cases import load_navigation_pack  # noqa: E402
from groundnut.navigation_eval import run_navigation_evaluation  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--lexical-max-nodes", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    result = run_navigation_evaluation(
        load_navigation_pack(args.pack),
        args.corpus_root,
        (
            FullInjectionNavigator(),
            LexicalStructureNavigator(max_nodes=args.lexical_max_nodes),
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_count": result["case_count"],
                "summaries": result["summaries"],
                "sha256": result["sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

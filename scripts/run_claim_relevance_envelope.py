#!/usr/bin/env python3
"""Observe a pinned reranker's scores over claim/excerpt anchor strata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from groundnut.adapters import RerankerQuestionRelevance  # noqa: E402
from groundnut.relevance_envelope import run_relevance_envelope  # noqa: E402
from run_relevance_exploration import _PinnedSequenceReranker  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--model-licence-spdx", required=True)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    claim_rows = json.loads(args.claims.read_text())["claims"]
    comparison_rows = {
        row["claim_id"]: row
        for row in json.loads(args.comparison.read_text())["rows"]
    }
    cases = []
    for claim in claim_rows:
        excerpt = claim.get("source_excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            continue
        comparison = comparison_rows.get(claim["claim_id"], {})
        anchor = comparison.get("groundnut_anchor")
        cases.append(
            {
                "case_id": claim["claim_id"],
                "query_text": claim["claim_text"],
                "evidence_text": excerpt,
                "stratum": "anchor_null" if anchor is None else f"anchor_{anchor}",
            }
        )

    import transformers

    scorer = RerankerQuestionRelevance(
        scorer=_PinnedSequenceReranker(args.model_path, args.device),
        model=args.model_name,
        revision=args.model_revision,
        package_version=transformers.__version__,
        model_licence_spdx=args.model_licence_spdx,
        model_source=f"https://huggingface.co/{args.model_name}",
    )
    result = run_relevance_envelope(cases, scorer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "summary": result["summary"], "sha256": result["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

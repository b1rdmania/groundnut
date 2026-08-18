#!/usr/bin/env python3
"""Run an unthresholded question-relevance scorer over the frozen dev cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.adapters import (  # noqa: E402
    LexicalQuestionRelevance,
    RerankerQuestionRelevance,
)
from groundnut.relevance_exploration import run_relevance_exploration  # noqa: E402
from groundnut.support_agent_screen import AgentSuggestion  # noqa: E402
from groundnut.support_review import PilotReviewManifest, PilotReviewRow  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-jsonl", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--suggestions", type=Path, required=True)
    parser.add_argument("--scorer", choices=("lexical", "bge-reranker"), required=True)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--model-name")
    parser.add_argument("--model-revision")
    parser.add_argument("--model-licence-spdx")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    rows = tuple(
        PilotReviewRow.from_mapping(json.loads(line))
        for line in args.review_jsonl.read_text().splitlines()
        if line.strip()
    )
    manifest = PilotReviewManifest.from_mapping(json.loads(args.manifest.read_text()), rows)
    suggestions = tuple(
        AgentSuggestion.from_mapping(json.loads(line))
        for line in args.suggestions.read_text().splitlines()
        if line.strip()
    )
    if args.scorer == "lexical":
        scorer = LexicalQuestionRelevance()
    else:
        if not all(
            (
                args.model_path,
                args.model_name,
                args.model_revision,
                args.model_licence_spdx,
            )
        ):
            parser.error(
                "bge-reranker requires --model-path, --model-name, "
                "--model-revision, and --model-licence-spdx"
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
    result = run_relevance_exploration(manifest, suggestions, scorer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"output": str(args.output), "metrics": result["metrics"], "sha256": result["sha256"]},
            indent=2,
        )
    )
    return 0


class _PinnedSequenceReranker:
    def __init__(self, model_path: Path, device: str) -> None:
        if not model_path.is_dir():
            raise ValueError("reranker requires a pinned local model directory")
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS was requested but is unavailable")
        self.torch = torch
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_path, local_files_only=True
        ).to(device).eval()

    def score_pair(self, question: str, evidence_text: str) -> dict[str, float]:
        encoded = self.tokenizer(
            question,
            evidence_text,
            max_length=512,
            truncation="only_second",
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self.torch.no_grad():
            logit = float(self.model(**encoded).logits.reshape(-1)[0].cpu().item())
        return {"logit": logit, "score": float(self.torch.sigmoid(self.torch.tensor(logit)))}


if __name__ == "__main__":
    raise SystemExit(main())

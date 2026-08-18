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
    ExtractiveQuestionAnswerRelevance,
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
    parser.add_argument(
        "--scorer", choices=("lexical", "bge-reranker", "extractive-qa"), required=True
    )
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

        adapter = (
            RerankerQuestionRelevance
            if args.scorer == "bge-reranker"
            else ExtractiveQuestionAnswerRelevance
        )
        backend = (
            _PinnedSequenceReranker(args.model_path, args.device)
            if args.scorer == "bge-reranker"
            else _PinnedExtractiveQA(args.model_path, args.device)
        )
        scorer = adapter(
            scorer=backend,
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


class _PinnedExtractiveQA:
    def __init__(self, model_path: Path, device: str) -> None:
        if not model_path.is_dir():
            raise ValueError("extractive-QA scorer requires a pinned local model directory")
        import torch
        from transformers import AutoModelForQuestionAnswering, AutoTokenizer

        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS was requested but is unavailable")
        self.torch = torch
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForQuestionAnswering.from_pretrained(
            model_path, local_files_only=True
        ).to(device).eval()

    def score_pair(self, question: str, evidence_text: str) -> dict[str, object]:
        import hashlib

        encoded = self.tokenizer(
            question,
            evidence_text,
            max_length=512,
            truncation="only_second",
            return_offsets_mapping=True,
            return_tensors="pt",
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        sequence_ids = encoded.sequence_ids(0)
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self.torch.no_grad():
            output = self.model(**encoded)
        starts = output.start_logits[0].cpu()
        ends = output.end_logits[0].cpu()
        null_logit = float(starts[0] + ends[0])
        context_indexes = [
            index for index, sequence_id in enumerate(sequence_ids) if sequence_id == 1
        ]
        if not context_indexes:
            return {
                "score": 0.0,
                "answer_start": 0,
                "answer_end": 0,
                "answer_sha256": hashlib.sha256(b"").hexdigest(),
                "best_span_logit": null_logit,
                "null_logit": null_logit,
            }
        best_score = float("-inf")
        best = (0, 0)
        for start in context_indexes:
            for end in context_indexes:
                if end < start or end - start >= 64:
                    continue
                score = float(starts[start] + ends[end])
                if score > best_score:
                    best_score = score
                    best = (offsets[start][0], offsets[end][1])
        answer = evidence_text[best[0] : best[1]]
        answerability = float(self.torch.sigmoid(self.torch.tensor(best_score - null_logit)))
        return {
            "score": answerability,
            "answer_start": best[0],
            "answer_end": best[1],
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "best_span_logit": best_score,
            "null_logit": null_logit,
        }


if __name__ == "__main__":
    raise SystemExit(main())

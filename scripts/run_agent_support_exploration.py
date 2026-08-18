#!/usr/bin/env python3
"""Run a pinned support component over one agent-screened development batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.adapters import (  # noqa: E402
    AlignScoreAdapter,
    LettuceDetectAdapter,
    MiniCheckAdapter,
    SummaCAdapter,
)
from groundnut.support import ExactSupportDetector  # noqa: E402
from groundnut.support_agent_screen import AgentSuggestion  # noqa: E402
from groundnut.support_exploration import run_agent_exploration  # noqa: E402
from groundnut.support_review import PilotReviewManifest, PilotReviewRow  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-jsonl", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--suggestions", type=Path, required=True)
    parser.add_argument(
        "--detector",
        choices=(
            "exact",
            "lettuce",
            "minicheck-flan",
            "alignscore-nli",
            "alignscore-qa",
            "summac-zs",
        ),
        required=True,
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--checkpoint-path", type=Path)
    parser.add_argument("--backbone-path", type=Path)
    parser.add_argument("--backbone-revision")
    parser.add_argument("--model-name")
    parser.add_argument("--model-revision")
    parser.add_argument("--model-licence-spdx")
    parser.add_argument("--model-source")
    parser.add_argument("--summac-model-key", default="vitc")
    parser.add_argument("--granularity", default="sentence")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--package-version", default="0.2.3")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = tuple(
        PilotReviewRow.from_mapping(json.loads(line))
        for line in args.review_jsonl.read_text().splitlines()
        if line.strip()
    )
    manifest_value = json.loads(args.manifest.read_text())
    manifest = PilotReviewManifest.from_mapping(manifest_value, rows)
    suggestions = tuple(
        AgentSuggestion.from_mapping(json.loads(line))
        for line in args.suggestions.read_text().splitlines()
        if line.strip()
    )
    if args.detector == "exact":
        detector = ExactSupportDetector()
    elif args.detector == "lettuce":
        if not args.model_path or not args.model_name or not args.model_revision:
            parser.error("lettuce requires --model-path, --model-name, --model-revision")
        detector = LettuceDetectAdapter(
            model=args.model_name,
            revision=args.model_revision,
            span_threshold=args.threshold if args.threshold is not None else 0.5,
            model_path=args.model_path,
            installed_package_version=args.package_version,
            model_licence_spdx=args.model_licence_spdx or "NOASSERTION",
            model_source=args.model_source or args.model_name,
        )
    elif args.detector == "minicheck-flan":
        if not args.model_path or not args.model_name or not args.model_revision:
            parser.error(
                "minicheck-flan requires --model-path, --model-name, --model-revision"
            )
        detector = MiniCheckAdapter(
            scorer=_PinnedMiniCheckFlanScorer(args.model_path),
            model=args.model_name,
            revision=args.model_revision,
            installed_package_version=args.package_version,
            model_licence_spdx=args.model_licence_spdx or "NOASSERTION",
            model_source=args.model_source or args.model_name,
        )
    elif args.detector.startswith("alignscore-"):
        if not all(
            (
                args.checkpoint_path,
                args.backbone_path,
                args.backbone_revision,
                args.model_name,
                args.model_revision,
            )
        ):
            parser.error(
                "AlignScore requires --checkpoint-path, --backbone-path, "
                "--backbone-revision, --model-name, and --model-revision"
            )
        detector = AlignScoreAdapter(
            mode="nli" if args.detector == "alignscore-nli" else "qa",
            model=args.model_name,
            revision=args.model_revision,
            checkpoint_path=args.checkpoint_path,
            backbone_path=args.backbone_path,
            backbone_revision=args.backbone_revision,
            installed_package_version=args.package_version,
            model_licence_spdx=args.model_licence_spdx or "MIT",
            model_source=args.model_source or args.model_name,
        )
    else:
        if not all(
            (
                args.model_path,
                args.model_name,
                args.model_revision,
                args.model_licence_spdx,
                args.model_source,
            )
        ):
            parser.error(
                "summac-zs requires --model-path, --model-name, --model-revision, "
                "--model-licence-spdx, and --model-source"
            )
        detector = SummaCAdapter(
            scorer=_PinnedSummaCZSScorer(
                args.model_path,
                model_key=args.summac_model_key,
                granularity=args.granularity,
                device=args.device,
            ),
            model=args.model_name,
            revision=args.model_revision,
            installed_package_version=args.package_version,
            model_licence_spdx=args.model_licence_spdx,
            model_source=args.model_source,
            threshold=args.threshold if args.threshold is not None else 0.0,
            granularity=args.granularity,
            aggregation="summac-zs:max-mean:entailment-minus-contradiction",
            sentence_splitter_id="groundnut.regex-sentence.v1",
            runtime_device=args.device,
        )
    result = run_agent_exploration(manifest, suggestions, detector)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "detector": result["detector"],
        "group_count": result["group_count"],
        "case_count": result["case_count"],
        "score": result["score"],
        "eligible_for_admission": result["eligible_for_admission"],
        "sha256": result["sha256"],
    }, indent=2))


class _PinnedMiniCheckFlanScorer:
    """Local-path implementation of MiniCheck-Flan's published scoring rule."""

    def __init__(self, model_path: Path) -> None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        if not model_path.is_dir():
            raise ValueError("MiniCheck scorer requires a pinned local model directory")
        self.torch = torch
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_path, local_files_only=True
        )
        if torch.backends.mps.is_available():
            self.model.to("mps")
        self.model.eval()
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)

    def score(self, docs: list[str], claims: list[str]):
        if len(docs) != 1 or len(claims) != 1:
            raise ValueError("pinned MiniCheck scorer expects one case")
        from nltk.tokenize import sent_tokenize

        chunks = []
        current = []
        words = 0
        for sentence in sent_tokenize(docs[0]):
            count = len(sentence.split())
            if current and words + count > 500:
                chunks.append(" ".join(current))
                current, words = [], 0
            current.append(sentence)
            words += count
        if current:
            chunks.append(" ".join(current))
        chunks = chunks or [docs[0]]
        values = [
            "predict: " + chunk + self.tokenizer.eos_token + claims[0]
            for chunk in chunks
        ]
        inputs = self.tokenizer(
            values,
            max_length=2048,
            truncation=True,
            padding=True,
            return_tensors="pt",
        )
        device = self.model.device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        decoder = self.torch.zeros(
            (len(chunks), 1), dtype=self.torch.long, device=device
        )
        with self.torch.no_grad():
            logits = self.model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                decoder_input_ids=decoder,
            ).logits.squeeze(1)
            probabilities = self.torch.softmax(logits[:, [3, 209]], dim=-1)[:, 1]
        raw = [float(value) for value in probabilities.cpu()]
        support_probability = max(raw)
        return [int(support_probability > 0.5)], [support_probability], chunks, [raw]


class _PinnedSummaCZSScorer:
    """SummaC-ZS with an explicitly local NLI model and no network loading."""

    def __init__(
        self, model_path: Path, *, model_key: str, granularity: str, device: str
    ) -> None:
        import torch
        from summac.model_summac import SummaCZS
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if not model_path.is_dir():
            raise ValueError("SummaC scorer requires a pinned local model directory")
        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("SummaC MPS device is unavailable")
        self.scorer = SummaCZS(
            model_name=model_key,
            granularity=granularity,
            op1="max",
            op2="mean",
            use_ent=True,
            use_con=True,
            imager_load_cache=False,
            use_cache=False,
            device=device,
        )
        self.scorer.imager.tokenizer = AutoTokenizer.from_pretrained(
            model_path, local_files_only=True
        )
        self.scorer.imager.model = AutoModelForSequenceClassification.from_pretrained(
            model_path, local_files_only=True
        ).to(device).eval()
        self.scorer.imager.split_sentences = _groundnut_sentences

    def score_one(self, *, original: str, generated: str):
        return self.scorer.score_one(original, generated)


def _groundnut_sentences(text: str) -> list[str]:
    """Offline sentence split used by the pinned SummaC experiment."""
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if len(sentence.strip()) > 10
    ]


if __name__ == "__main__":
    main()

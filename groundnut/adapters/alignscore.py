"""Optional pinned AlignScore adapter with full Groundnut label preservation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ..support import DetectorDecision, DetectorIdentity, configuration_sha256


_MODES = {"nli": "three_way_nli", "qa": "question_answer_binary"}


class AlignScoreAdapter:
    """Run a pinned AlignScore checkpoint without its lossy score-only façade."""

    def __init__(
        self,
        *,
        mode: str,
        model: str,
        revision: str,
        checkpoint_path: str | Path | None = None,
        backbone_path: str | Path | None = None,
        backbone_revision: str | None = None,
        installed_package_version: str = "0.1.3",
        backend: Any | None = None,
        sentence_splitter: Callable[[str], list[str]] | None = None,
    ) -> None:
        if mode not in _MODES:
            raise ValueError(f"unsupported AlignScore mode: {mode}")
        if backend is None and (not backbone_revision or checkpoint_path is None):
            raise ValueError("AlignScore local loading requires pinned checkpoint/backbone")
        config = {
            "mode": mode,
            "mapping": "groundnut-alignscore/v1",
            "chunk_words": 350,
            "backbone_revision": backbone_revision,
        }
        self.identity = DetectorIdentity(
            adapter=f"groundnut.alignscore.{mode}.v1",
            model=model,
            revision=revision,
            package="alignscore",
            package_version=installed_package_version,
            configuration_sha256=configuration_sha256(config),
        )
        self.mode = mode
        self.backend = backend or _PinnedAlignScoreBackend(
            checkpoint_path=Path(checkpoint_path),
            backbone_path=Path(backbone_path) if backbone_path else None,
            sentence_splitter=sentence_splitter,
        )

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision:
        if self.mode == "qa" and not question:
            raise ValueError("question-conditioned AlignScore requires a question")
        result = self.backend.predict(
            source_text=source_text,
            claim_text=claim_text,
            question=question,
            mode=self.mode,
        )
        probabilities = tuple(float(value) for value in result["probabilities"])
        expected_length = 3 if self.mode == "nli" else 2
        if len(probabilities) != expected_length or any(
            value < 0 or value > 1 for value in probabilities
        ) or abs(sum(probabilities) - 1.0) > 1e-5:
            raise ValueError("AlignScore returned invalid probabilities")
        index = max(range(len(probabilities)), key=probabilities.__getitem__)
        labels = (
            ("supported", "insufficient", "contradicted")
            if self.mode == "nli"
            else ("insufficient", "supported")
        )
        label = labels[index]
        normalized = {
            "mode": self.mode,
            "probabilities": list(probabilities),
            "selected_chunk_sha256": str(result["selected_chunk_sha256"]),
        }
        return DetectorDecision(
            label=label,
            confidence=probabilities[index],
            reason=(
                f"AlignScore {_MODES[self.mode]} selected {label} from the "
                "highest-support evidence chunk."
            ),
            raw_output_sha256=hashlib.sha256(
                json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )


class _PinnedAlignScoreBackend:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        backbone_path: Path | None,
        sentence_splitter: Callable[[str], list[str]] | None,
    ) -> None:
        if not checkpoint_path.is_file() or backbone_path is None or not backbone_path.is_dir():
            raise ValueError("AlignScore requires pinned local checkpoint and backbone")
        import torch
        from torch import nn
        from transformers import AutoConfig, AutoTokenizer, RobertaModel

        self.torch = torch
        config = AutoConfig.from_pretrained(backbone_path, local_files_only=True)
        self.tokenizer = AutoTokenizer.from_pretrained(backbone_path, local_files_only=True)
        self.base_model = RobertaModel(config, add_pooling_layer=True)
        self.tri_layer = nn.Linear(config.hidden_size, 3)
        self.bin_layer = nn.Linear(config.hidden_size, 2)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        state = checkpoint["state_dict"]
        base = {
            key.removeprefix("base_model."): value
            for key, value in state.items()
            if key.startswith("base_model.")
        }
        missing, unexpected = self.base_model.load_state_dict(base, strict=False)
        if any(key != "embeddings.position_ids" for key in unexpected) or missing:
            raise ValueError(
                f"AlignScore checkpoint/backbone mismatch: missing={missing}, "
                f"unexpected={unexpected}"
            )
        self.tri_layer.load_state_dict(
            {"weight": state["tri_layer.weight"], "bias": state["tri_layer.bias"]}
        )
        self.bin_layer.load_state_dict(
            {"weight": state["bin_layer.weight"], "bias": state["bin_layer.bias"]}
        )
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.base_model.to(self.device).eval()
        self.tri_layer.to(self.device).eval()
        self.bin_layer.to(self.device).eval()
        self.sentence_splitter = sentence_splitter or _nltk_sentences

    def predict(
        self, *, source_text: str, claim_text: str, question: str | None, mode: str
    ) -> dict[str, Any]:
        chunks = _alignscore_chunks(source_text, self.sentence_splitter)
        hypothesis = f"{question} {claim_text}" if mode == "qa" else claim_text
        encoded = self.tokenizer(
            chunks,
            [hypothesis] * len(chunks),
            truncation="only_first",
            padding=True,
            max_length=self.tokenizer.model_max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self.torch.no_grad():
            output = self.base_model(**encoded)
            logits = (
                self.tri_layer(output.pooler_output)
                if mode == "nli"
                else self.bin_layer(output.pooler_output)
            )
            probabilities = self.torch.softmax(logits, dim=-1)
        support_index = 0 if mode == "nli" else 1
        selected = int(probabilities[:, support_index].argmax().item())
        return {
            "probabilities": probabilities[selected].cpu().tolist(),
            "selected_chunk_sha256": hashlib.sha256(chunks[selected].encode()).hexdigest(),
        }


def _alignscore_chunks(
    text: str, sentence_splitter: Callable[[str], list[str]]
) -> list[str]:
    sentences = sentence_splitter(text) or [text]
    target_count = len(text.strip().split()) // 350 + 1
    per_chunk = max(len(sentences) // target_count, 1)
    return [
        " ".join(sentences[index : index + per_chunk])
        for index in range(0, len(sentences), per_chunk)
    ]


def _nltk_sentences(text: str) -> list[str]:
    from nltk.tokenize import sent_tokenize

    return sent_tokenize(text)

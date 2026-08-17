"""Optional LettuceDetect adapter with conservative Groundnut semantics."""

from __future__ import annotations

from importlib.metadata import version as package_version
import json
import hashlib
from pathlib import Path
from typing import Any

from ..support import (
    DetectorDecision,
    DetectorIdentity,
    SupportSpan,
    configuration_sha256,
)


DEFAULT_QUESTION = "Is every part of this claim supported by the supplied source?"


class LettuceDetectAdapter:
    """Map Lettuce unsupported spans into Groundnut support decisions.

    Actual model loading requires a local model directory. This prevents a
    moving Hugging Face ref from being downloaded behind an allegedly pinned
    revision. Tests and research runners may inject an already-loaded backend.
    """

    def __init__(
        self,
        *,
        model: str,
        revision: str,
        span_threshold: float = 0.5,
        taxonomy_head: str | None = None,
        backend: Any | None = None,
        model_path: str | Path | None = None,
        taxonomy_head_path: str | Path | None = None,
        installed_package_version: str | None = None,
        fallback_question: str = DEFAULT_QUESTION,
    ) -> None:
        if not 0.0 <= span_threshold <= 1.0:
            raise ValueError("Lettuce span_threshold must be between 0 and 1")
        if not fallback_question.strip():
            raise ValueError("Lettuce fallback question must not be empty")
        config = {
            "span_threshold": span_threshold,
            "taxonomy_head": taxonomy_head,
            "fallback_question": fallback_question,
            "mapping": "groundnut-lettuce/v1",
        }
        if installed_package_version is None:
            installed_package_version = package_version("lettucedetect")
        self.identity = DetectorIdentity(
            adapter="groundnut.lettuce.v1",
            model=model,
            revision=revision,
            package="lettucedetect",
            package_version=installed_package_version,
            configuration_sha256=configuration_sha256(config),
        )
        self.span_threshold = span_threshold
        self.fallback_question = fallback_question
        self.backend = (
            backend
            if backend is not None
            else self._load_backend(
                model_path=model_path,
                taxonomy_head=taxonomy_head,
                taxonomy_head_path=taxonomy_head_path,
            )
        )

    @staticmethod
    def _load_backend(
        *,
        model_path: str | Path | None,
        taxonomy_head: str | None,
        taxonomy_head_path: str | Path | None,
    ) -> Any:
        if model_path is None or not Path(model_path).is_dir():
            raise ValueError("Lettuce adapter requires a pinned local model directory")
        if taxonomy_head and (
            taxonomy_head_path is None or not Path(taxonomy_head_path).is_dir()
        ):
            raise ValueError(
                "typed Lettuce adapter requires a pinned local taxonomy-head directory"
            )
        from lettucedetect.models.inference import HallucinationDetector

        kwargs: dict[str, Any] = {
            "method": "transformer",
            "model_path": str(model_path),
        }
        if taxonomy_head:
            kwargs["taxonomy_head"] = str(taxonomy_head_path)
        return HallucinationDetector(**kwargs)

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision:
        raw = self.backend.predict(
            context=[source_text],
            question=question or self.fallback_question,
            answer=claim_text,
            output_format="spans",
            min_confidence=self.span_threshold,
        )
        if not isinstance(raw, list):
            raise TypeError("Lettuce span output must be a list")
        normalized = [_normalize_span(row) for row in raw]
        raw_hash = _hash_json(normalized)
        spans = tuple(_support_span(row) for row in normalized)
        if not spans:
            return DetectorDecision(
                label="supported",
                confidence=None,
                reason="LettuceDetect returned no unsupported spans.",
                raw_output_sha256=raw_hash,
            )
        contradiction = any(
            row.get("category", "").casefold() == "contradiction"
            for row in normalized
        )
        confidences = [span.confidence for span in spans if span.confidence is not None]
        return DetectorDecision(
            label="contradicted" if contradiction else "insufficient",
            confidence=max(confidences) if confidences else None,
            reason=(
                "LettuceDetect returned an explicitly typed contradiction span."
                if contradiction
                else "LettuceDetect returned unsupported spans without an explicit "
                "contradiction type."
            ),
            spans=spans,
            raw_output_sha256=raw_hash,
        )


def _normalize_span(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Lettuce span must be an object")
    confidence = value.get("confidence")
    return {
        "start": int(value["start"]),
        "end": int(value["end"]),
        "text": str(value["text"]),
        "confidence": float(confidence) if confidence is not None else None,
        "category": str(value.get("category", "")),
        "subcategory": str(value.get("subcategory", "")),
    }


def _support_span(value: dict[str, Any]) -> SupportSpan:
    labels = [value["category"], value["subcategory"]]
    label = "/".join(part for part in labels if part) or "unsupported"
    return SupportSpan(
        start=value["start"],
        end=value["end"],
        text=value["text"],
        label=label,
        confidence=value["confidence"],
    )


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

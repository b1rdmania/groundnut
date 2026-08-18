"""Benchmark-only SummaC adapter with a replayable component signal."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..signals import (
    ComponentLicence,
    ComponentSignal,
    component_input_sha256,
)
from ..support import DetectorDecision, DetectorIdentity, configuration_sha256


SUMMAC_CODE_SOURCE = "https://github.com/tingofurro/summac"


class SummaCAdapter:
    """Expose SummaC consistency as one binary support signal.

    Groundnut requires an injected scorer so the adapter cannot download model
    files behind a recorded revision. The scorer must implement SummaC's
    ``score_one(original=..., generated=...)`` interface.
    """

    def __init__(
        self,
        *,
        scorer: Any,
        model: str,
        revision: str,
        installed_package_version: str,
        model_licence_spdx: str,
        model_source: str,
        threshold: float = 0.0,
        raw_score_min: float = -1.0,
        raw_score_max: float = 1.0,
        granularity: str = "sentence",
        aggregation: str = "published",
        sentence_splitter_id: str = "summac.nltk.sent_tokenize",
        runtime_device: str = "cpu",
    ) -> None:
        if scorer is None:
            raise ValueError("SummaC adapter requires an injected pinned scorer")
        if raw_score_min >= raw_score_max:
            raise ValueError("SummaC raw score range must increase")
        if not raw_score_min <= threshold <= raw_score_max:
            raise ValueError("SummaC threshold must be inside its raw score range")
        if not all(
            value.strip()
            for value in (
                granularity,
                aggregation,
                sentence_splitter_id,
                runtime_device,
            )
        ):
            raise ValueError(
                "SummaC granularity, aggregation, and sentence splitter are required"
            )
        config = {
            "mapping": "groundnut-summac/v1",
            "threshold": threshold,
            "raw_score_min": raw_score_min,
            "raw_score_max": raw_score_max,
            "granularity": granularity,
            "aggregation": aggregation,
            "sentence_splitter_id": sentence_splitter_id,
            "runtime_device": runtime_device,
            "unsupported_mapping": "insufficient",
            "question_used": False,
        }
        self.identity = DetectorIdentity(
            adapter="groundnut.summac.v1",
            model=model,
            revision=revision,
            package="summac",
            package_version=installed_package_version,
            configuration_sha256=configuration_sha256(config),
        )
        self.licence = ComponentLicence(
            code_spdx="Apache-2.0",
            code_source=SUMMAC_CODE_SOURCE,
            model_spdx=model_licence_spdx,
            model_source=model_source,
        )
        self.scorer = scorer
        self.threshold = threshold
        self.raw_score_min = raw_score_min
        self.raw_score_max = raw_score_max
        self.granularity = granularity
        self.aggregation = aggregation
        self.sentence_splitter_id = sentence_splitter_id
        self.runtime_device = runtime_device

    def assess_signal(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> ComponentSignal:
        result = self.scorer.score_one(original=source_text, generated=claim_text)
        if isinstance(result, Mapping):
            if "score" not in result:
                raise ValueError("SummaC output did not contain a score")
            score = float(result["score"])
            normalized_output = _json_value(result)
        else:
            score = float(result)
            normalized_output = {"score": score}
        if not self.raw_score_min <= score <= self.raw_score_max:
            raise ValueError("SummaC returned an invalid consistency score")
        supported = score >= self.threshold
        normalized_score = (score - self.raw_score_min) / (
            self.raw_score_max - self.raw_score_min
        )
        raw_output = {
            "published_output": normalized_output,
            "raw_consistency_score": score,
            "normalized_consistency_score": normalized_score,
            "threshold": self.threshold,
            "raw_score_range": [self.raw_score_min, self.raw_score_max],
            "granularity": self.granularity,
            "aggregation": self.aggregation,
            "sentence_splitter_id": self.sentence_splitter_id,
            "runtime_device": self.runtime_device,
            "question_used": False,
        }
        return ComponentSignal(
            role="entailment",
            label="supported" if supported else "insufficient",
            scores={"consistency_normalized": normalized_score},
            input_sha256=component_input_sha256(
                source_text=source_text,
                claim_text=claim_text,
                question=question,
            ),
            component=self.identity,
            licence=self.licence,
            raw_output=raw_output,
            note=(
                "SummaC aggregate consistency met the frozen threshold. It did "
                "not assess question relevance or establish truth."
                if supported
                else "SummaC aggregate consistency missed the frozen threshold. "
                "Its binary score cannot distinguish contradiction from "
                "insufficient evidence or assess question relevance."
            ),
        )

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision:
        decision, _ = self.assess_with_signal(
            source_text=source_text,
            claim_text=claim_text,
            question=question,
        )
        return decision

    def assess_with_signal(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> tuple[DetectorDecision, ComponentSignal]:
        """Return one decision and its lossless component signal in one call."""
        signal = self.assess_signal(
            source_text=source_text,
            claim_text=claim_text,
            question=question,
        )
        score = signal.scores["consistency_normalized"]
        supported = signal.label == "supported"
        return (
            DetectorDecision(
                label=signal.label,
                confidence=score if supported else 1.0 - score,
                reason=signal.note,
                raw_output_sha256=signal.raw_output_sha256,
            ),
            signal,
        )


def _json_value(value: Any) -> Any:
    """Convert SummaC/numpy output into deterministic JSON without dropping it."""
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_value(value.tolist())
    if hasattr(value, "item"):
        return _json_value(value.item())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"SummaC returned unsupported raw output: {type(value).__name__}")

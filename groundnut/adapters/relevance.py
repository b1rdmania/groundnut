"""Deterministic baseline for question-to-evidence relevance."""

from __future__ import annotations

import re
from typing import Any, Protocol

from ..signals import ComponentLicence, ComponentSignal, component_input_sha256
from ..support import DetectorIdentity, configuration_sha256


_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "from", "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "what", "when", "where", "which", "who", "why", "with",
}


class LexicalQuestionRelevance:
    """Measure query-term recall as a transparent baseline, not a verdict."""

    def __init__(self) -> None:
        self.identity = DetectorIdentity(
            adapter="groundnut.question-relevance.lexical.v1",
            model="query-token-recall",
            revision="1",
            package="groundnut",
            package_version="1",
            configuration_sha256=configuration_sha256(
                {"tokenizer": "lowercase-alphanumeric", "stop_words": sorted(_STOP)}
            ),
        )
        self.licence = ComponentLicence(
            code_spdx="Apache-2.0",
            code_source="https://github.com/b1rdmania/groundnut",
        )

    def score(self, *, question: str, evidence_text: str) -> ComponentSignal:
        question_tokens = _tokens(question)
        evidence_tokens = _tokens(evidence_text)
        shared = question_tokens & evidence_tokens
        score = len(shared) / len(question_tokens) if question_tokens else 0.0
        raw = {
            "question_tokens": sorted(question_tokens),
            "evidence_tokens": sorted(evidence_tokens),
            "shared_tokens": sorted(shared),
            "query_token_recall": score,
        }
        return ComponentSignal(
            role="relevance",
            label="unthresholded",
            scores={"relevant": score},
            input_sha256=component_input_sha256(
                source_text=evidence_text, claim_text="", question=question
            ),
            component=self.identity,
            licence=self.licence,
            raw_output=raw,
            note=(
                "Transparent query-token recall baseline. It measures lexical "
                "relatedness only and does not decide support or contradiction."
            ),
        )


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN.findall(value.casefold()) if token not in _STOP}


class PairReranker(Protocol):
    def score_pair(self, question: str, evidence_text: str) -> dict[str, Any]: ...


class RerankerQuestionRelevance:
    """Expose a pinned passage reranker as an unthresholded relevance signal."""

    def __init__(
        self,
        *,
        scorer: PairReranker,
        model: str,
        revision: str,
        package_version: str,
        model_licence_spdx: str,
        model_source: str,
    ) -> None:
        self.scorer = scorer
        self.identity = DetectorIdentity(
            adapter="groundnut.question-relevance.reranker.v1",
            model=model,
            revision=revision,
            package="transformers",
            package_version=package_version,
            configuration_sha256=configuration_sha256(
                {"input_order": ["question", "evidence_text"], "max_length": 512}
            ),
        )
        self.licence = ComponentLicence(
            code_spdx="Apache-2.0",
            code_source="https://github.com/huggingface/transformers",
            model_spdx=model_licence_spdx,
            model_source=model_source,
        )

    def score(self, *, question: str, evidence_text: str) -> ComponentSignal:
        result = self.scorer.score_pair(question, evidence_text)
        score = float(result["score"])
        if not 0.0 <= score <= 1.0:
            raise ValueError("reranker relevance score must be between zero and one")
        raw = {"logit": float(result["logit"]), "score": score}
        return ComponentSignal(
            role="relevance",
            label="unthresholded",
            scores={"relevant": score},
            input_sha256=component_input_sha256(
                source_text=evidence_text, claim_text="", question=question
            ),
            component=self.identity,
            licence=self.licence,
            raw_output=raw,
            note=(
                "Question-to-evidence passage reranker score. It measures relevance "
                "only and does not decide support, contradiction, or truth."
            ),
        )


class ExtractiveQuestionAnswerRelevance:
    """Expose answerability from a pinned extractive-QA model as relevance."""

    def __init__(
        self,
        *,
        scorer: PairReranker,
        model: str,
        revision: str,
        package_version: str,
        model_licence_spdx: str,
        model_source: str,
    ) -> None:
        self.scorer = scorer
        self.identity = DetectorIdentity(
            adapter="groundnut.question-relevance.extractive-qa.v1",
            model=model,
            revision=revision,
            package="transformers",
            package_version=package_version,
            configuration_sha256=configuration_sha256(
                {
                    "input_order": ["question", "evidence_text"],
                    "max_length": 512,
                    "max_answer_tokens": 64,
                    "score": "sigmoid(best_context_span_logit-null_logit)",
                }
            ),
        )
        self.licence = ComponentLicence(
            code_spdx="Apache-2.0",
            code_source="https://github.com/huggingface/transformers",
            model_spdx=model_licence_spdx,
            model_source=model_source,
        )

    def score(self, *, question: str, evidence_text: str) -> ComponentSignal:
        result = self.scorer.score_pair(question, evidence_text)
        score = float(result["score"])
        if not 0.0 <= score <= 1.0:
            raise ValueError("extractive-QA answerability must be between zero and one")
        raw = {
            "answer_start": int(result["answer_start"]),
            "answer_end": int(result["answer_end"]),
            "answer_sha256": str(result["answer_sha256"]),
            "best_span_logit": float(result["best_span_logit"]),
            "null_logit": float(result["null_logit"]),
            "answerability": score,
        }
        return ComponentSignal(
            role="relevance",
            label="unthresholded",
            scores={"relevant": score},
            input_sha256=component_input_sha256(
                source_text=evidence_text, claim_text="", question=question
            ),
            component=self.identity,
            licence=self.licence,
            raw_output=raw,
            note=(
                "Extractive-QA answerability over the candidate evidence only. "
                "It does not decide whether the extracted answer supports the claim."
            ),
        )

import copy
import hashlib
import json

import pytest

from groundnut.adapters.relevance import (
    ExtractiveQuestionAnswerRelevance,
    LexicalQuestionRelevance,
    RerankerQuestionRelevance,
)
from groundnut.relevance_exploration import (
    _average_precision,
    _paired_group_ranking,
    _roc_auc,
    validate_relevance_exploration,
)


def test_lexical_relevance_is_question_to_evidence_only():
    scorer = LexicalQuestionRelevance()
    relevant = scorer.score(
        question="What is the governing law?",
        evidence_text="This agreement is governed by Delaware law.",
    )
    irrelevant = scorer.score(
        question="What is the governing law?",
        evidence_text="The agreement renews for one year.",
    )
    assert relevant.role == "relevance"
    assert relevant.scores["relevant"] > irrelevant.scores["relevant"]
    assert relevant.raw_output_sha256 == relevant.to_dict()["raw_output_sha256"]


def test_threshold_free_metrics_preserve_relevance_independence():
    rows = [
        {"case_id": "a", "expected_relevant": True, "relevance_score": 0.9},
        {"case_id": "b", "expected_relevant": True, "relevance_score": 0.8},
        {"case_id": "c", "expected_relevant": False, "relevance_score": 0.1},
    ]
    assert _roc_auc(rows) == 1.0
    assert _average_precision(rows) == 1.0


def test_paired_group_ranking_requires_every_relevance_kind():
    rows = [
        {"input_sha256": "g", "kind": "verbatim_supported", "relevance_score": 0.9},
        {"input_sha256": "g", "kind": "paraphrase_supported", "relevance_score": 0.8},
        {"input_sha256": "g", "kind": "contradicted", "relevance_score": 0.7},
        {"input_sha256": "g", "kind": "present_irrelevant", "relevance_score": 0.1},
    ]
    result = _paired_group_ranking(rows)
    assert result["all_three_relevant_above_irrelevant_rate"] == 1.0
    assert result["pairwise_win_rate"]["contradicted"] == 1.0


def test_reranker_preserves_raw_logit_and_licence():
    class FakeScorer:
        def score_pair(self, question, evidence_text):
            return {"logit": 1.5, "score": 0.817574}

    scorer = RerankerQuestionRelevance(
        scorer=FakeScorer(),
        model="example/reranker",
        revision="abc123",
        package_version="5.0",
        model_licence_spdx="MIT",
        model_source="https://example.test/model",
    )
    signal = scorer.score(question="What law?", evidence_text="Delaware law")
    assert signal.raw_output["logit"] == 1.5
    assert signal.licence.model_spdx == "MIT"


def test_extractive_qa_preserves_answerability_without_support_claim():
    class FakeScorer:
        def score_pair(self, question, evidence_text):
            return {
                "score": 0.8,
                "answer_start": 0,
                "answer_end": 8,
                "answer_sha256": "a" * 64,
                "best_span_logit": 4.0,
                "null_logit": 2.0,
            }

    scorer = ExtractiveQuestionAnswerRelevance(
        scorer=FakeScorer(),
        model="example/qa",
        revision="abc123",
        package_version="5.0",
        model_licence_spdx="CC-BY-4.0",
        model_source="https://example.test/qa",
    )
    signal = scorer.score(question="What law?", evidence_text="Delaware")
    assert signal.scores["relevant"] == 0.8
    assert "does not decide" in signal.note


def test_relevance_receipt_rejects_tampering():
    value = {
        "schema": "groundnut-relevance-exploration/v1",
        "eligible_for_admission": False,
    }
    value["sha256"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    validate_relevance_exploration(value)
    changed = copy.deepcopy(value)
    changed["eligible_for_admission"] = True
    with pytest.raises(ValueError, match="self-hash"):
        validate_relevance_exploration(changed)

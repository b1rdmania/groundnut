import pytest

from groundnut.adapters.relevance import LexicalQuestionRelevance
from groundnut.relevance_envelope import run_relevance_envelope


def test_envelope_keeps_mechanical_strata_unlabelled():
    result = run_relevance_envelope(
        [
            {
                "case_id": "a",
                "query_text": "Governing law",
                "evidence_text": "Delaware law applies",
                "stratum": "anchor_found",
            },
            {
                "case_id": "b",
                "query_text": "Governing law",
                "evidence_text": "Twelve month term",
                "stratum": "anchor_fuzzy",
            },
        ],
        LexicalQuestionRelevance(),
    )
    assert result["qualification"] == "unlabelled_observation_only"
    assert result["eligible_for_admission"] is False
    assert set(result["summary"]) == {"anchor_found", "anchor_fuzzy"}
    assert "expected_relevant" not in result["rows"][0]


def test_envelope_rejects_duplicate_ids():
    case = {
        "case_id": "same",
        "query_text": "A claim",
        "evidence_text": "Some evidence",
        "stratum": "one",
    }
    with pytest.raises(ValueError, match="unique"):
        run_relevance_envelope([case, case], LexicalQuestionRelevance())

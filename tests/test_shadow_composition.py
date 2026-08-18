import copy

import pytest

from groundnut.shadow_composition import (
    compose_shadow_receipt,
    validate_shadow_receipt,
)


def _account(claim_id="c1", *, anchor="found", question="What was revenue?", failure=None):
    source = {"source_id": "s1", "uri": "https://example.test/a"}
    method = "fetch_failed" if failure else "exact"
    return {
        "assessment": {
            "verification": {
                "claim": {"claim_id": claim_id, "source": source, "question": question},
                "anchor": anchor,
                "method": method,
                "score": 1.0 if anchor == "found" else 0.5,
                "failure": failure,
            },
            "support": {
                "status": "insufficient",
                "decision": {"label": "insufficient", "confidence": 1.0},
                "detector": {"adapter": "groundnut.exact"},
            },
        }
    }


def test_shadow_composition_preserves_signals_but_withholds_without_admission():
    signal = {"label": "reranker", "scores": {"relevant": 0.99}}
    receipt = compose_shadow_receipt(
        [_account()], component_signals={"c1": [signal]}
    )
    validate_shadow_receipt(receipt)
    [row] = receipt["rows"]
    assert row["outcome"] == "withheld"
    assert row["reason"] == "no_semantic_component_admitted"
    assert row["experimental_signals"] == [signal]
    assert row["semantic_disagreement"]["state"] == "not_evaluated"


@pytest.mark.parametrize(
    ("account", "outcome", "reason"),
    [
        (_account(question=None), "withheld", "missing_verification_question"),
        (_account(anchor="ambiguous"), "needs_validation", "anchor_ambiguous"),
        (
            _account(anchor=None, failure="source_unreachable"),
            "source_unavailable",
            "source_unreachable",
        ),
    ],
)
def test_shadow_composition_fails_closed(account, outcome, reason):
    [row] = compose_shadow_receipt([account])["rows"]
    assert (row["outcome"], row["reason"]) == (outcome, reason)


def test_shadow_composition_receipt_detects_tampering():
    receipt = compose_shadow_receipt([_account()])
    changed = copy.deepcopy(receipt)
    changed["rows"][0]["outcome"] = "needs_validation"
    with pytest.raises(ValueError, match="self-hash mismatch"):
        validate_shadow_receipt(changed)

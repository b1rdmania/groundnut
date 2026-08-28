from dataclasses import replace
from pathlib import Path

import pytest

from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
from groundnut.support import (
    DetectorDecision,
    DetectorIdentity,
    ExactSupportDetector,
    SupportPolicy,
    SupportSpan,
    assess_claim_support,
)
from groundnut.support_eval import SupportGold, score_support
from groundnut.verification import Claim, verify_claim


REFERENCE = SourceReference("s1", "https://example.test/source")
SOURCE_TEXT = "Revenue was $14.2M. The supplier shall deliver the report."


def resolved(text=SOURCE_TEXT):
    return SourceResolution(
        source=ResolvedSource(
            reference=REFERENCE,
            text=text,
            fetched_at="2026-08-17T00:00:00Z",
            status=200,
            media_type="text/plain",
        )
    )


def policy_for(detector, threshold=0.8):
    return SupportPolicy(
        key="test_support",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=detector.identity,
        min_confidence=threshold,
    )


def verified(claim_text="Revenue was $14.2M.", excerpt="Revenue was $14.2M."):
    claim = Claim("c1", claim_text, source=REFERENCE, excerpt=excerpt)
    return verify_claim(claim, resolved())


class StubDetector:
    identity = DetectorIdentity("test.stub", "stub", "r1", "test", "1")

    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def assess(self, *, source_text, claim_text, question):
        self.calls += 1
        return self.decision


def test_exact_baseline_adds_support_without_mutating_anchor_result():
    detector = ExactSupportDetector()
    mechanical = verified()
    result = assess_claim_support(
        mechanical,
        resolved(),
        detector=detector,
        policy=policy_for(detector, 1.0),
    )

    assert mechanical.support == "not_assessed"
    assert result.verification is mechanical
    assert result.support.status == "supported"
    assert result.support.source_sha256 == resolved().source.record.sha256
    assert result.support.detector.sha256 == detector.identity.sha256
    assert result.support.to_dict()["decision"]["label"] == "supported"
    combined = result.to_dict()
    assert combined["verification"]["support"] == "not_assessed"
    assert combined["support"]["status"] == "supported"


def test_exact_absence_is_insufficient_not_contradicted():
    detector = ExactSupportDetector()
    result = assess_claim_support(
        verified("Revenue was approximately fourteen million dollars."),
        resolved(),
        detector=detector,
        policy=policy_for(detector, 1.0),
    )

    assert result.support.status == "insufficient"


def test_unavailable_source_fails_closed_without_calling_detector():
    detector = StubDetector(DetectorDecision("supported", 0.99, "supported"))
    failure = SourceResolution(source=None, failure="source_paywalled")
    mechanical = verify_claim(
        Claim("c1", "Claim", source=REFERENCE, excerpt="excerpt"), failure
    )

    result = assess_claim_support(
        mechanical,
        failure,
        detector=detector,
        policy=policy_for(detector),
    )

    assert result.support.status == "source_unavailable"
    assert result.support.failure == "source_paywalled"
    assert result.support.decision is None
    assert detector.calls == 0


def test_bare_locator_is_source_unavailable_without_calling_detector():
    detector = StubDetector(DetectorDecision("supported", 0.99, "supported"))
    mechanical = verify_claim(
        Claim("c1", "Confidential claim.", locator="memo, page 7"), None
    )

    result = assess_claim_support(
        mechanical,
        None,
        detector=detector,
        policy=policy_for(detector),
    )

    assert result.support.status == "source_unavailable"
    assert result.support.failure == "unresolvable_source"
    assert result.support.decision is None
    assert detector.calls == 0


def test_low_confidence_cannot_become_supported():
    detector = StubDetector(DetectorDecision("supported", 0.79, "weak support"))
    result = assess_claim_support(
        verified(), resolved(), detector=detector, policy=policy_for(detector, 0.8)
    )

    assert result.support.status == "insufficient"
    assert result.support.decision.label == "supported"


def test_unscored_decision_requires_policy_to_explicitly_allow_it():
    detector = StubDetector(DetectorDecision("supported", None, "thresholded model"))
    strict = assess_claim_support(
        verified(), resolved(), detector=detector, policy=policy_for(detector, 0.8)
    )
    detector.calls = 0
    unscored_policy = policy_for(detector, None)
    allowed = assess_claim_support(
        verified(), resolved(), detector=detector, policy=unscored_policy
    )

    assert strict.support.status == "insufficient"
    assert allowed.support.status == "supported"


def test_detector_failure_and_bad_span_are_not_assessed():
    bad_span = SupportSpan(0, 7, "not the", "contradiction", 0.9)
    detector = StubDetector(
        DetectorDecision("contradicted", 0.9, "bad offsets", (bad_span,))
    )
    result = assess_claim_support(
        verified(), resolved(), detector=detector, policy=policy_for(detector)
    )

    assert result.support.status == "not_assessed"
    assert result.support.failure == "detector_error:ValueError"
    assert result.support.decision is None


def test_support_input_hash_excludes_host_local_claim_id():
    detector = ExactSupportDetector()
    policy = policy_for(detector, 1.0)
    first = assess_claim_support(
        verified(), resolved(), detector=detector, policy=policy
    ).support
    other_claim = Claim(
        "host-specific-id", "Revenue was $14.2M.", source=REFERENCE,
        excerpt="Revenue was $14.2M.",
    )
    second = assess_claim_support(
        verify_claim(other_claim, resolved()),
        resolved(),
        detector=detector,
        policy=policy,
    ).support

    assert first.input_sha256 == second.input_sha256

    different_question = Claim(
        "c3", "Revenue was $14.2M.", source=REFERENCE,
        excerpt="Revenue was $14.2M.", question="Was revenue audited?",
    )
    third = assess_claim_support(
        verify_claim(different_question, resolved()),
        resolved(),
        detector=detector,
        policy=policy,
    ).support
    assert first.input_sha256 != third.input_sha256


def test_raw_detector_output_hash_must_be_explicit_sha256():
    with pytest.raises(ValueError, match="raw_output_sha256"):
        DetectorDecision("insufficient", 1.0, "no", raw_output_sha256="opaque")


def test_policy_pins_exact_detector_identity(tmp_path):
    path = tmp_path / "policy.json"
    source = SupportPolicy(
        key="frozen",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=StubDetector.identity,
        min_confidence=0.9,
    )
    import json

    path.write_text(json.dumps(source.canonical_payload()))
    loaded = SupportPolicy.from_json(path)
    wrong = StubDetector(DetectorDecision("supported", 1.0, "yes"))
    wrong.identity = replace(wrong.identity, revision="r2")

    assert loaded.sha256 == source.sha256
    with pytest.raises(ValueError, match="does not match"):
        assess_claim_support(
            verified(), resolved(), detector=wrong, policy=loaded
        )


def test_shipped_policy_pins_the_exact_baseline():
    root = Path(__file__).parents[1]
    loaded = SupportPolicy.from_json(
        root / "policies" / "exact-support-baseline-v1.json"
    )

    assert loaded.detector == ExactSupportDetector.identity
    assert loaded.min_confidence == 1.0


def assessments(*statuses):
    detector = StubDetector(DetectorDecision("supported", 1.0, "yes"))
    policy = policy_for(detector)
    rows = []
    for index, status in enumerate(statuses, 1):
        decision = DetectorDecision(status, 1.0, status)
        current = StubDetector(decision)
        current.identity = detector.identity
        mechanical = verify_claim(
            Claim(f"c{index}", SOURCE_TEXT, source=REFERENCE, excerpt=SOURCE_TEXT),
            resolved(),
        )
        rows.append(
            assess_claim_support(
                mechanical, resolved(), detector=current, policy=policy
            ).support
        )
    return rows


def test_support_scorer_is_one_to_one_and_counts_missing_predictions():
    gold = [
        SupportGold("c1", "supported", "verbatim"),
        SupportGold("c2", "contradicted", "negation"),
        SupportGold("c3", "insufficient", "irrelevant"),
    ]
    rows = assessments("supported", "insufficient")

    score = score_support(gold, rows)

    assert score["total"] == 3
    assert score["predicted"] == 2
    assert score["missing"] == 1
    assert score["accuracy"] == pytest.approx(1 / 3)
    assert score["by_kind"]["verbatim"]["accuracy"] == 1.0
    assert score["confusion"]["contradicted"]["insufficient"] == 1
    assert score["confusion"]["insufficient"]["missing"] == 1


def test_support_scorer_rejects_duplicate_or_unknown_predictions():
    gold = [SupportGold("c1", "supported", "verbatim")]
    row = assessments("supported")[0]

    with pytest.raises(ValueError, match="duplicate prediction"):
        score_support(gold, [row, row])
    with pytest.raises(ValueError, match="unknown case"):
        score_support([], [row])

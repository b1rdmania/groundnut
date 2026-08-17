from dataclasses import replace

import pytest

from groundnut.checker import ClaimCheckReport, check_claims
from groundnut.run_manifest import ArtifactDigest
from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
from groundnut.support import (
    DetectorIdentity,
    ExactSupportDetector,
    SupportPolicy,
)
from groundnut.verification import Claim


SOURCE = "Revenue was $14.2M. The supplier shall deliver within thirty days."
REFERENCE = SourceReference("s1", "memory://s1")


def resolution(reference=REFERENCE, text=SOURCE):
    return SourceResolution(
        source=ResolvedSource(
            reference=reference,
            text=text,
            fetched_at="2026-08-17T00:00:00Z",
            media_type="text/plain",
        )
    )


def exact_policy():
    detector = ExactSupportDetector()
    policy = SupportPolicy(
        key="exact",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=detector.identity,
        min_confidence=1.0,
    )
    return detector, policy


def test_batch_report_keeps_mechanical_and_semantic_layers_separate():
    detector, policy = exact_policy()
    paywall = SourceReference("s2", "https://example.test/paywall")
    claims = [
        Claim("supported", "Revenue was $14.2M.", source=REFERENCE,
              excerpt="Revenue was $14.2M."),
        Claim("paraphrase", "Revenue was about fourteen million dollars.",
              source=REFERENCE),
        Claim("unavailable", "A sourced claim", source=paywall),
        Claim("unsourced", "An analyst opinion", declared_analysis=True),
    ]
    report = check_claims(
        claims,
        {
            REFERENCE: resolution(),
            paywall: SourceResolution(source=None, failure="source_paywalled"),
        },
        detector=detector,
        policy=policy,
    )

    by_id = {row.support.claim_id: row for row in report.claims}
    assert by_id["supported"].verification.support == "not_assessed"
    assert by_id["supported"].support.status == "supported"
    assert by_id["paraphrase"].support.status == "insufficient"
    assert by_id["unavailable"].support.status == "source_unavailable"
    assert by_id["unsourced"].support.status == "not_assessed"
    assert report.complete is False
    assert report.summary["semantic_assessments"] == 2
    assert report.summary["unresolved_assessments"] == 2
    assert report.summary["mechanical"]["citation_coverage"] == 0.75


def test_missing_resolution_is_visible_source_unavailable():
    detector, policy = exact_policy()
    report = check_claims(
        [Claim("c1", "Claim", source=REFERENCE)],
        {},
        detector=detector,
        policy=policy,
    )

    assert report.claims[0].verification.failure == "source_unreachable"
    assert report.claims[0].support.status == "source_unavailable"
    assert report.complete is False


class BrokenDetector:
    identity = DetectorIdentity("test.broken", "broken", "r1", "test", "1")

    def assess(self, *, source_text, claim_text, question):
        raise RuntimeError("model failed")


def test_detector_failure_is_not_assessed_and_does_not_abort_batch():
    detector = BrokenDetector()
    policy = SupportPolicy(
        key="broken",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=detector.identity,
        min_confidence=0.8,
    )
    report = check_claims(
        [Claim("c1", "Revenue was $14.2M.", source=REFERENCE)],
        {REFERENCE: resolution()},
        detector=detector,
        policy=policy,
    )

    assert report.claims[0].support.status == "not_assessed"
    assert report.claims[0].support.failure == "detector_error:RuntimeError"
    assert report.complete is False


def test_report_hash_is_order_stable_and_manifest_ready():
    detector, policy = exact_policy()
    claims = [
        Claim("b", "Absent claim", source=REFERENCE),
        Claim("a", "Revenue was $14.2M.", source=REFERENCE),
    ]
    first = check_claims(
        claims, {REFERENCE: resolution()}, detector=detector, policy=policy
    )
    second = check_claims(
        reversed(claims),
        {REFERENCE: resolution()},
        detector=detector,
        policy=policy,
    )
    artifact = ArtifactDigest.from_value("claim_check", first.to_dict())

    assert first.sha256 == second.sha256
    assert artifact.schema == "groundnut-claim-check-report/v1"
    assert len(artifact.sha256) == 64


def test_duplicate_claims_and_mismatched_layers_are_rejected():
    detector, policy = exact_policy()
    claim = Claim("same", "Revenue was $14.2M.", source=REFERENCE)
    with pytest.raises(ValueError, match="duplicate claim id"):
        check_claims(
            [claim, claim],
            {REFERENCE: resolution()},
            detector=detector,
            policy=policy,
        )

    valid = check_claims(
        [claim], {REFERENCE: resolution()}, detector=detector, policy=policy
    )
    bad_support = replace(valid.claims[0].support, claim_id="different")
    with pytest.raises(ValueError, match="identities differ"):
        ClaimCheckReport(
            policy_key=valid.policy_key,
            policy_sha256=valid.policy_sha256,
            claims=(replace(valid.claims[0], support=bad_support),),
        )

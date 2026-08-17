from dataclasses import replace

import pytest

from groundnut.provenance import sha256_text
from groundnut.run_manifest import ArtifactDigest
from groundnut.support import ExactSupportDetector, SupportPolicy
from groundnut.support_cases import CASE_KINDS, SupportCase, SupportProbe
from groundnut.support_runner import SupportProbeRun, run_support_probe


SOURCE = (
    "Opening material. "
    "The supplier shall deliver the audited report within thirty days. "
    + "Padding. " * 30
    + "The agreement is governed by English law. Closing material."
)
ORIGINAL = "The supplier shall deliver the audited report within thirty days."
START = SOURCE.index(ORIGINAL)
QUESTION = "What is the supplier's delivery obligation?"
CLAIMS = {
    "verbatim_supported": ORIGINAL,
    "paraphrase_supported": "The supplier must provide an audited report within 30 days.",
    "contradicted": "The supplier need not deliver an audited report.",
    "present_irrelevant": "The agreement is governed by English law.",
}


def probe():
    cases = []
    for kind, expected in CASE_KINDS.items():
        cases.append(
            SupportCase(
                case_id=f"g1-{kind}",
                group_id="g1",
                kind=kind,
                expected_status=expected,
                source_id="s1",
                source_sha256=sha256_text(SOURCE),
                original_start=START,
                original_end=START + len(ORIGINAL),
                original_text=ORIGINAL,
                question=QUESTION,
                claim_text=CLAIMS[kind],
            )
        )
    return SupportProbe(tuple(cases))


def exact():
    detector = ExactSupportDetector()
    policy = SupportPolicy(
        key="exact",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=detector.identity,
        min_confidence=1.0,
    )
    return detector, policy


def test_runner_uses_identical_group_windows_and_scores_exact_baseline():
    detector, policy = exact()
    result = run_support_probe(
        probe(),
        {"s1": SOURCE},
        max_context_characters=120,
        detector=detector,
        policy=policy,
    )

    assert len({row.sha256 for row in result.contexts}) == 1
    assert result.score["accuracy"] == 0.5
    assert result.score["by_kind"]["paraphrase_supported"]["accuracy"] == 0.0
    assert result.complete is True
    assert len(result.sha256) == 64


def test_probe_run_is_order_stable_and_manifest_ready():
    detector, policy = exact()
    first = run_support_probe(
        probe(), {"s1": SOURCE}, max_context_characters=120,
        detector=detector, policy=policy,
    )
    reordered = SupportProbeRun(
        probe_sha256=first.probe_sha256,
        max_context_characters=first.max_context_characters,
        policy_key=first.policy_key,
        policy_sha256=first.policy_sha256,
        detector=first.detector,
        contexts=tuple(reversed(first.contexts)),
        gold=tuple(reversed(first.gold)),
        assessments=tuple(reversed(first.assessments)),
    )
    artifact = ArtifactDigest.from_value("support_probe", first.to_dict())

    assert first.sha256 == reordered.sha256
    assert artifact.schema == "groundnut-support-probe-run/v1"


def test_probe_run_rejects_mixed_policy_rows():
    detector, policy = exact()
    valid = run_support_probe(
        probe(), {"s1": SOURCE}, max_context_characters=120,
        detector=detector, policy=policy,
    )
    changed_support = replace(
        valid.assessments[0].support, policy_key="different"
    )
    changed = replace(valid.assessments[0], support=changed_support)

    with pytest.raises(ValueError, match="identity differs"):
        replace(valid, assessments=(changed, *valid.assessments[1:]))


def test_source_tampering_fails_before_detector_execution():
    detector, policy = exact()
    with pytest.raises(ValueError, match="source hash mismatch"):
        run_support_probe(
            probe(), {"s1": SOURCE + "tampered"}, max_context_characters=120,
            detector=detector, policy=policy,
        )

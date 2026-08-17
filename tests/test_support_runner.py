from dataclasses import replace

import pytest

from groundnut.provenance import sha256_text
from groundnut.probe_plan import SupportProbePlan
from groundnut.run_manifest import ArtifactDigest
from groundnut.support import ExactSupportDetector, SupportPolicy
from groundnut.support_cases import CASE_KINDS, CaseProvenance, SupportCase, SupportProbe
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
        provenance_kind = {
            "verbatim_supported": "attested",
            "paraphrase_supported": "authored",
            "contradicted": "derived",
            "present_irrelevant": "adjudicated",
        }[kind]
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
                provenance=CaseProvenance(
                    kind=provenance_kind,
                    source="test-fixture",
                    source_record_id=f"g1:{kind}",
                    method="test construction",
                    parent_case_ids=("g1-verbatim_supported",)
                    if provenance_kind == "derived"
                    else (),
                    reviewed_by=("test-reviewer",)
                    if provenance_kind == "adjudicated"
                    else (),
                ),
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


def plan(*, group_count=1, context=120, probe_hash=None):
    return SupportProbePlan(
        key="support-pilot-v1",
        frozen_at="2026-08-17T00:00:00Z",
        group_count=group_count,
        sampling_seed=991,
        probe_sha256=probe_hash or probe().sha256,
        source_pool_sha256="1" * 64,
        excluded_pool_sha256="2" * 64,
        max_context_characters=context,
        primary_metric="macro_f1",
        minimum_improvement=0.05,
        baseline_policy_keys=("exact",),
        detector_policy_keys=("lettuce-v2", "minicheck"),
        lexical_overlap_min=0.2,
        lexical_overlap_max=0.8,
    )


def test_runner_uses_identical_group_windows_and_scores_exact_baseline():
    detector, policy = exact()
    result = run_support_probe(
        probe(),
        {"s1": SOURCE},
        max_context_characters=120,
        detector=detector,
        policy=policy,
        plan=plan(),
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
        detector=detector, policy=policy, plan=plan(),
    )
    reordered = SupportProbeRun(
        plan_key=first.plan_key,
        plan_sha256=first.plan_sha256,
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
    assert artifact.schema == "groundnut-support-probe-run/v2"


def test_probe_run_rejects_mixed_policy_rows():
    detector, policy = exact()
    valid = run_support_probe(
        probe(), {"s1": SOURCE}, max_context_characters=120,
        detector=detector, policy=policy, plan=plan(),
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
            detector=detector, policy=policy, plan=plan(),
        )


def test_runner_refuses_unregistered_or_post_hoc_protocol_changes():
    detector, policy = exact()
    with pytest.raises(ValueError, match="group count differs"):
        run_support_probe(
            probe(), {"s1": SOURCE}, max_context_characters=120,
            detector=detector, policy=policy, plan=plan(group_count=2),
        )
    with pytest.raises(ValueError, match="context size differs"):
        run_support_probe(
            probe(), {"s1": SOURCE}, max_context_characters=120,
            detector=detector, policy=policy, plan=plan(context=200),
        )
    with pytest.raises(ValueError, match="probe hash differs"):
        run_support_probe(
            probe(), {"s1": SOURCE}, max_context_characters=120,
            detector=detector, policy=policy, plan=plan(probe_hash="f" * 64),
        )

import hashlib
import json

import pytest

from groundnut.probe_plan import SupportProbePlan
from groundnut.provenance import sha256_text
from groundnut.support import (
    DetectorDecision,
    DetectorIdentity,
    ExactSupportDetector,
    SupportPolicy,
)
from groundnut.support_admission import RecordedProbeRun, evaluate_support_admission
from groundnut.support_bakeoff import run_support_bakeoff
from groundnut.support_cases import (
    CASE_KINDS,
    CaseProvenance,
    SupportCase,
    SupportProbe,
    contexts_sha256,
)
from groundnut.support_gate_cli import main as gate_main
from groundnut.support_runner import run_support_probe


SOURCE = (
    "The supplier shall deliver the audited report within thirty days. "
    "The agreement is governed by English law."
)
ORIGINAL = "The supplier shall deliver the audited report within thirty days."
START = SOURCE.index(ORIGINAL)
QUESTION = "What is the supplier's delivery obligation?"
CLAIMS = {
    "verbatim_supported": ORIGINAL,
    "paraphrase_supported": "The supplier must provide an audited report within 30 days.",
    "contradicted": "The supplier is not required to deliver an audited report.",
    "present_irrelevant": "The agreement is governed by English law.",
}


def rehash(value):
    canonical = {key: item for key, item in value.items() if key != "sha256"}
    value["sha256"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class FixtureDetector:
    def __init__(self, *, regress_verbatim=False):
        self.regress_verbatim = regress_verbatim
        name = "regressing" if regress_verbatim else "perfect"
        self.identity = DetectorIdentity(
            adapter=f"test.{name}",
            model=name,
            revision="fixture-1",
            package="tests",
            package_version="1",
        )

    def assess(self, *, source_text, claim_text, question):
        if self.regress_verbatim and claim_text == ORIGINAL:
            label = "insufficient"
        elif "governed by" in claim_text:
            label = "insufficient"
        elif "not required" in claim_text:
            label = "contradicted"
        else:
            label = "supported"
        return DetectorDecision(label=label, confidence=1.0, reason="fixture")


def probe():
    rows = []
    for kind, expected in CASE_KINDS.items():
        provenance_kind = {
            "verbatim_supported": "attested",
            "paraphrase_supported": "authored",
            "contradicted": "derived",
            "present_irrelevant": "adjudicated",
        }[kind]
        rows.append(
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
                present_start=(
                    START
                    if kind == "verbatim_supported"
                    else SOURCE.index(CLAIMS[kind])
                    if kind == "present_irrelevant"
                    else None
                ),
                present_end=(
                    START + len(ORIGINAL)
                    if kind == "verbatim_supported"
                    else SOURCE.index(CLAIMS[kind]) + len(CLAIMS[kind])
                    if kind == "present_irrelevant"
                    else None
                ),
                provenance=CaseProvenance(
                    kind=provenance_kind,
                    source="fixture",
                    source_record_id=f"g1:{kind}",
                    method="fixture",
                    parent_case_ids=("g1-verbatim_supported",)
                    if provenance_kind == "derived"
                    else (),
                    reviewed_by=("human:r1",)
                    if provenance_kind == "adjudicated"
                    else (),
                ),
            )
        )
    return SupportProbe(tuple(rows))


def setup_runs():
    current_probe = probe()
    exact = ExactSupportDetector()
    perfect = FixtureDetector()
    regressing = FixtureDetector(regress_verbatim=True)
    policies = {
        key: SupportPolicy(
            key=key,
            version="1",
            frozen_at="2026-08-17T00:00:00Z",
            detector=detector.identity,
            min_confidence=1.0,
        )
        for key, detector in (
            ("exact", exact),
            ("perfect", perfect),
            ("regressing", regressing),
        )
    }
    plan = SupportProbePlan(
        key="support-admission-test",
        frozen_at="2026-08-17T00:00:00Z",
        group_count=1,
        sampling_seed=991,
        probe_sha256=current_probe.sha256,
        source_pool_sha256="a" * 64,
        excluded_pool_sha256="b" * 64,
        review_manifest_sha256="c" * 64,
        build_attempt=1,
        contexts_sha256=contexts_sha256(
            current_probe.contexts({"s1": SOURCE}, len(SOURCE))
        ),
        max_context_characters=len(SOURCE),
        primary_metric="macro_f1",
        minimum_improvement=0.05,
        baseline_policy_keys=("exact",),
        detector_policy_keys=("perfect", "regressing"),
        policy_hashes={key: policy.sha256 for key, policy in policies.items()},
        lexical_overlap_min=0.2,
        lexical_overlap_max=0.8,
    )

    def run(detector, key):
        return run_support_probe(
            current_probe,
            {"s1": SOURCE},
            max_context_characters=len(SOURCE),
            detector=detector,
            policy=policies[key],
            plan=plan,
        )

    return plan, run(exact, "exact"), run(perfect, "perfect"), run(regressing, "regressing")


def current_probe_for(plan):
    current = probe()
    assert current.sha256 == plan.probe_sha256
    return current


def test_admission_recomputes_scores_and_passes_a_real_improvement():
    plan, baseline, perfect, _ = setup_runs()
    baseline_record = RecordedProbeRun.from_mapping(baseline.to_dict())
    candidate_record = RecordedProbeRun.from_mapping(perfect.to_dict())

    report = evaluate_support_admission(
        plan, baseline_record, candidate_record, probe=current_probe_for(plan)
    )

    assert report.passed is True
    assert report.improvement >= plan.minimum_improvement
    assert not any(row["regression"] for row in report.by_kind.values())
    assert len(report.sha256) == 64


def test_admission_fails_material_kind_regression_even_with_aggregate_gain():
    plan, baseline, _, regressing = setup_runs()
    report = evaluate_support_admission(
        plan,
        RecordedProbeRun.from_mapping(baseline.to_dict()),
        RecordedProbeRun.from_mapping(regressing.to_dict()),
        probe=current_probe_for(plan),
    )

    assert report.candidate_value > report.baseline_value
    assert report.passed is False
    assert any("verbatim_supported" in failure for failure in report.failures)


def test_recorded_run_rejects_a_rehashed_but_fabricated_score():
    _, _, perfect, _ = setup_runs()
    value = json.loads(json.dumps(perfect.to_dict()))
    value["score"]["accuracy"] = 0.123
    rehash(value)

    with pytest.raises(ValueError, match="score does not match"):
        RecordedProbeRun.from_mapping(value)


def test_recorded_run_rejects_rehashed_detector_identity_tampering():
    _, _, perfect, _ = setup_runs()
    value = json.loads(json.dumps(perfect.to_dict()))
    value["detector"]["model"] = "different-model"
    rehash(value)

    with pytest.raises(ValueError, match="detector identity hash mismatch"):
        RecordedProbeRun.from_mapping(value)


def test_recorded_run_rejects_context_rows_not_shared_by_gold():
    _, _, perfect, _ = setup_runs()
    value = json.loads(json.dumps(perfect.to_dict()))
    value["contexts"][0]["case_id"] = "unknown-case"
    rehash(value)

    with pytest.raises(ValueError, match="assessment source hash differs"):
        RecordedProbeRun.from_mapping(value)


def test_admission_rejects_gold_rows_that_are_not_the_frozen_probe():
    plan, baseline, perfect, _ = setup_runs()
    # Internally consistent run over different cases, with the frozen probe
    # hash pasted in from the plan. Only the loaded probe can catch this.
    forged = json.loads(json.dumps(perfect.to_dict()).replace("g1-", "g9-"))
    rehash(forged)
    with pytest.raises(ValueError, match="not the frozen probe cases"):
        evaluate_support_admission(
            plan,
            RecordedProbeRun.from_mapping(baseline.to_dict()),
            RecordedProbeRun.from_mapping(forged),
            probe=current_probe_for(plan),
        )


def test_admission_rejects_rehashed_runs_with_fabricated_contexts():
    plan, baseline, perfect, _ = setup_runs()

    def forge_contexts(run):
        value = json.loads(json.dumps(run.to_dict()))
        for row in value["contexts"]:
            row["sha256"] = "d" * 64
        for row in value["assessments"]:
            row["support"]["source_sha256"] = "d" * 64
        rehash(value)
        return RecordedProbeRun.from_mapping(value)

    with pytest.raises(ValueError, match="not the frozen probe contexts"):
        evaluate_support_admission(
            plan,
            forge_contexts(baseline),
            forge_contexts(perfect),
            probe=current_probe_for(plan),
        )


def test_support_gate_cli_writes_replayable_report(tmp_path):
    plan, baseline, perfect, _ = setup_runs()
    plan_path = tmp_path / "plan.json"
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "admission.json"
    probe_path = tmp_path / "probe.jsonl"
    plan_path.write_text(json.dumps(plan.to_dict()))
    probe_path.write_text(
        "".join(json.dumps(case.canonical_payload()) + "\n" for case in current_probe_for(plan).cases)
    )
    baseline_path.write_text(json.dumps(baseline.to_dict()))
    candidate_path.write_text(json.dumps(perfect.to_dict()))

    code = gate_main(
        [
            "--plan",
            str(plan_path),
            "--probe",
            str(probe_path),
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
            "--out",
            str(output_path),
        ]
    )

    assert code == 0
    assert json.loads(output_path.read_text())["passed"] is True


def test_bakeoff_runs_every_frozen_policy_and_writes_hashed_artifacts(tmp_path):
    current_probe = probe()
    detectors = {
        "exact": ExactSupportDetector(),
        "perfect": FixtureDetector(),
    }
    policies = {
        key: SupportPolicy(
            key=key,
            version="1",
            frozen_at="2026-08-17T00:00:00Z",
            detector=detector.identity,
            min_confidence=1.0,
        )
        for key, detector in detectors.items()
    }
    plan = SupportProbePlan(
        key="bakeoff-test",
        frozen_at="2026-08-17T00:00:00Z",
        group_count=1,
        sampling_seed=991,
        probe_sha256=current_probe.sha256,
        source_pool_sha256="a" * 64,
        excluded_pool_sha256="b" * 64,
        review_manifest_sha256="c" * 64,
        build_attempt=1,
        contexts_sha256=contexts_sha256(
            current_probe.contexts({"s1": SOURCE}, len(SOURCE))
        ),
        max_context_characters=len(SOURCE),
        primary_metric="macro_f1",
        minimum_improvement=0.05,
        baseline_policy_keys=("exact",),
        detector_policy_keys=("perfect",),
        policy_hashes={key: policy.sha256 for key, policy in policies.items()},
        lexical_overlap_min=0.2,
        lexical_overlap_max=0.8,
    )

    bakeoff = run_support_bakeoff(
        current_probe,
        {"s1": SOURCE},
        plan,
        detectors,
        policies,
    )
    manifest = bakeoff.write(tmp_path)

    assert bakeoff.admissions["perfect"].passed is True
    assert json.loads(manifest.read_text())["sha256"] == bakeoff.sha256
    assert (tmp_path / "exact.run.json").exists()
    assert (tmp_path / "perfect.admission.json").exists()

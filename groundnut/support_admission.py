"""Deterministic admission gate for recorded semantic-support probe runs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .probe_plan import SupportProbePlan
from .support import DETECTOR_LABELS, DetectorIdentity
from .support_cases import CASE_KINDS, SupportProbe
from .support_eval import SupportGold, score_support


ADMISSION_SCHEMA = "groundnut-support-admission/v1"
RUN_SCHEMA = "groundnut-support-probe-run/v3"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class _RecordedPrediction:
    claim_id: str
    status: str


@dataclass(frozen=True)
class RecordedProbeRun:
    sha256: str
    plan_key: str
    plan_sha256: str
    probe_sha256: str
    max_context_characters: int
    policy_key: str
    policy_sha256: str
    detector_sha256: str
    contexts: tuple[tuple[str, str, int], ...]
    gold: tuple[SupportGold, ...]
    predictions: tuple[_RecordedPrediction, ...]
    complete: bool
    score: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecordedProbeRun":
        if value.get("schema") != RUN_SCHEMA:
            raise ValueError(f"unsupported support-probe run schema: {value.get('schema')}")
        supplied_hash = str(value.get("sha256", ""))
        canonical = {key: item for key, item in value.items() if key != "sha256"}
        actual_hash = _sha256_json(canonical)
        if supplied_hash != actual_hash:
            raise ValueError("support-probe run self-hash mismatch")
        plan = value.get("plan")
        policy = value.get("policy")
        detector = value.get("detector")
        if not all(isinstance(item, Mapping) for item in (plan, policy, detector)):
            raise ValueError("support-probe run identities are missing")
        digests = (
            supplied_hash,
            str(plan.get("sha256", "")),
            str(value.get("probe_sha256", "")),
            str(policy.get("sha256", "")),
            str(detector.get("sha256", "")),
        )
        if not all(_SHA256.fullmatch(digest) for digest in digests):
            raise ValueError("support-probe run identities require lowercase SHA-256")
        detector_identity = DetectorIdentity.from_mapping(detector)
        if detector_identity.sha256 != detector["sha256"]:
            raise ValueError("support-probe detector identity hash mismatch")
        contexts_value = value.get("contexts")
        gold_value = value.get("gold")
        assessments_value = value.get("assessments")
        if not all(
            isinstance(item, list)
            for item in (contexts_value, gold_value, assessments_value)
        ):
            raise ValueError("support-probe run rows are missing")
        if not all(isinstance(row, Mapping) for row in contexts_value):
            raise ValueError("support-probe context rows are invalid")
        contexts = tuple(
            sorted(
                (
                    str(row["case_id"]),
                    str(row["sha256"]),
                    int(row["characters"]),
                )
                for row in contexts_value
            )
        )
        context_ids = [case_id for case_id, _, _ in contexts]
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("support-probe contexts contain duplicate case ids")
        if any(
            not case_id.strip()
            or not _SHA256.fullmatch(digest)
            or characters < 1
            for case_id, digest, characters in contexts
        ):
            raise ValueError("support-probe context rows are invalid")
        gold = tuple(
            sorted(
                (
                    SupportGold(
                        case_id=str(row["case_id"]),
                        expected_status=str(row["expected_status"]),
                        kind=str(row["kind"]),
                    )
                    for row in gold_value
                ),
                key=lambda row: row.case_id,
            )
        )
        context_by_id = {case_id: digest for case_id, digest, _ in contexts}
        predictions = []
        for row in assessments_value:
            support = row.get("support") if isinstance(row, Mapping) else None
            if not isinstance(support, Mapping):
                raise ValueError("support-probe assessment has no support row")
            support_policy = support.get("policy")
            support_detector = support.get("detector")
            if not isinstance(support_policy, Mapping) or not isinstance(
                support_detector, Mapping
            ):
                raise ValueError("support-probe assessment identities are missing")
            if (
                support_policy.get("key") != policy.get("key")
                or support_policy.get("sha256") != policy.get("sha256")
            ):
                raise ValueError("support-probe assessment policy identity differs")
            nested_detector = DetectorIdentity.from_mapping(support_detector)
            if (
                nested_detector.sha256 != support_detector.get("sha256")
                or nested_detector != detector_identity
            ):
                raise ValueError("support-probe assessment detector identity differs")
            claim_id = str(support["claim_id"])
            if support.get("source_sha256") != context_by_id.get(claim_id):
                raise ValueError("support-probe assessment source hash differs")
            predictions.append(
                _RecordedPrediction(
                    claim_id=claim_id,
                    status=str(support["status"]),
                )
            )
        predictions = tuple(sorted(predictions, key=lambda row: row.claim_id))
        recalculated = score_support(gold, predictions)  # type: ignore[arg-type]
        if value.get("score") != recalculated:
            raise ValueError("support-probe run score does not match recorded rows")
        complete = bool(value.get("complete"))
        expected_ids = {row.case_id for row in gold}
        predicted_ids = {row.claim_id for row in predictions}
        if expected_ids != set(context_ids):
            raise ValueError("support-probe context and gold case ids differ")
        expected_complete = (
            expected_ids == predicted_ids
            and all(row.status in DETECTOR_LABELS for row in predictions)
        )
        if complete != expected_complete:
            raise ValueError("support-probe run completeness does not match recorded rows")
        return cls(
            sha256=supplied_hash,
            plan_key=str(plan["key"]),
            plan_sha256=str(plan["sha256"]),
            probe_sha256=str(value["probe_sha256"]),
            max_context_characters=int(value["max_context_characters"]),
            policy_key=str(policy["key"]),
            policy_sha256=str(policy["sha256"]),
            detector_sha256=str(detector["sha256"]),
            contexts=contexts,
            gold=gold,
            predictions=predictions,
            complete=complete,
            score=recalculated,
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "RecordedProbeRun":
        return cls.from_mapping(json.loads(Path(path).read_text()))


@dataclass(frozen=True)
class SupportAdmissionReport:
    plan_key: str
    plan_sha256: str
    baseline_run_sha256: str
    candidate_run_sha256: str
    baseline_policy_key: str
    candidate_policy_key: str
    primary_metric: str
    baseline_value: float
    candidate_value: float
    improvement: float
    minimum_improvement: float
    by_kind: Mapping[str, Mapping[str, Any]]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": ADMISSION_SCHEMA,
            "plan": {"key": self.plan_key, "sha256": self.plan_sha256},
            "baseline": {
                "run_sha256": self.baseline_run_sha256,
                "policy_key": self.baseline_policy_key,
                "value": self.baseline_value,
            },
            "candidate": {
                "run_sha256": self.candidate_run_sha256,
                "policy_key": self.candidate_policy_key,
                "value": self.candidate_value,
            },
            "primary_metric": self.primary_metric,
            "improvement": self.improvement,
            "minimum_improvement": self.minimum_improvement,
            "by_kind": {key: dict(value) for key, value in sorted(self.by_kind.items())},
            "failures": list(self.failures),
            "passed": self.passed,
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def evaluate_support_admission(
    plan: SupportProbePlan,
    baseline: RecordedProbeRun,
    candidate: RecordedProbeRun,
    *,
    probe: SupportProbe,
) -> SupportAdmissionReport:
    """Compare frozen runs; fail on identity drift, weak gain, or kind regression.

    The probe itself is required. A run's ``probe_sha256`` is a self-declared
    string; only the loaded probe can prove that the recorded gold rows are the
    frozen cases and nothing else.
    """

    plan.validate_probe(probe.sha256, probe.group_count)
    _validate_run_against_plan(plan, baseline, role="baseline")
    _validate_run_against_plan(plan, candidate, role="candidate")
    _validate_run_against_probe(probe, baseline, role="baseline")
    _validate_run_against_probe(probe, candidate, role="candidate")
    if baseline.probe_sha256 != candidate.probe_sha256:
        raise ValueError("admission runs use different probes")
    if baseline.contexts != candidate.contexts:
        raise ValueError("admission runs use different context windows")
    if baseline.gold != candidate.gold:
        raise ValueError("admission runs use different gold rows")
    if baseline.policy_key not in plan.baseline_policy_keys:
        raise ValueError("baseline policy is not registered as a baseline")
    if candidate.policy_key not in plan.detector_policy_keys:
        raise ValueError("candidate policy is not registered as a detector")
    if plan.primary_metric not in {"macro_f1", "accuracy"}:
        raise ValueError(f"unsupported admission primary metric: {plan.primary_metric}")

    baseline_value = _metric(baseline.score, plan.primary_metric)
    candidate_value = _metric(candidate.score, plan.primary_metric)
    improvement = round(candidate_value - baseline_value, 12)
    failures = []
    if not baseline.complete:
        failures.append("baseline run is incomplete")
    if not candidate.complete:
        failures.append("candidate run is incomplete")
    if improvement < plan.minimum_improvement:
        failures.append(
            f"primary metric improvement {improvement:.6f} is below "
            f"{plan.minimum_improvement:.6f}"
        )

    by_kind = {}
    for kind in sorted(CASE_KINDS):
        baseline_kind = _kind_accuracy(baseline.score, kind)
        candidate_kind = _kind_accuracy(candidate.score, kind)
        regression = candidate_kind < baseline_kind
        by_kind[kind] = {
            "baseline_accuracy": baseline_kind,
            "candidate_accuracy": candidate_kind,
            "change": round(candidate_kind - baseline_kind, 12),
            "regression": regression,
        }
        if regression:
            failures.append(
                f"material kind regressed: {kind} "
                f"({baseline_kind:.6f} -> {candidate_kind:.6f})"
            )
    return SupportAdmissionReport(
        plan_key=plan.key,
        plan_sha256=plan.sha256,
        baseline_run_sha256=baseline.sha256,
        candidate_run_sha256=candidate.sha256,
        baseline_policy_key=baseline.policy_key,
        candidate_policy_key=candidate.policy_key,
        primary_metric=plan.primary_metric,
        baseline_value=baseline_value,
        candidate_value=candidate_value,
        improvement=improvement,
        minimum_improvement=plan.minimum_improvement,
        by_kind=by_kind,
        failures=tuple(failures),
    )


def _validate_run_against_plan(
    plan: SupportProbePlan, run: RecordedProbeRun, *, role: str
) -> None:
    if run.plan_key != plan.key or run.plan_sha256 != plan.sha256:
        raise ValueError(f"{role} run does not match frozen plan")
    if run.probe_sha256 != plan.probe_sha256:
        raise ValueError(f"{role} run does not match frozen probe")
    if run.max_context_characters != plan.max_context_characters:
        raise ValueError(f"{role} run does not match frozen context size")
    if run.policy_sha256 != plan.policy_sha256(run.policy_key):
        raise ValueError(f"{role} run does not match frozen policy hash")


def _validate_run_against_probe(
    probe: SupportProbe, run: RecordedProbeRun, *, role: str
) -> None:
    expected = {
        (case.case_id, case.kind, case.expected_status) for case in probe.cases
    }
    recorded = {(row.case_id, row.kind, row.expected_status) for row in run.gold}
    if recorded != expected or len(run.gold) != len(probe.cases):
        raise ValueError(f"{role} run gold rows are not the frozen probe cases")


def _metric(score: Mapping[str, Any], key: str) -> float:
    value = score.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"support score has no numeric {key}")
    return float(value)


def _kind_accuracy(score: Mapping[str, Any], kind: str) -> float:
    by_kind = score.get("by_kind")
    row = by_kind.get(kind) if isinstance(by_kind, Mapping) else None
    value = row.get("accuracy") if isinstance(row, Mapping) else None
    if not isinstance(value, (int, float)):
        raise ValueError(f"support score has no accuracy for material kind: {kind}")
    return float(value)


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()

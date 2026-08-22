"""Run every frozen support policy over one probe and compare to baseline."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .probe_plan import SupportProbePlan
from .support import SupportDetector, SupportPolicy
from .support_admission import SupportAdmissionReport, evaluate_support_admission
from .support_admission import RecordedProbeRun
from .support_cases import SupportProbe
from .support_runner import SupportProbeRun, run_support_probe


BAKEOFF_SCHEMA = "groundnut-support-bakeoff/v1"
_SAFE_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


@dataclass(frozen=True)
class SupportBakeoff:
    plan_key: str
    plan_sha256: str
    baseline_policy_key: str
    runs: Mapping[str, SupportProbeRun]
    admissions: Mapping[str, SupportAdmissionReport]

    def __post_init__(self) -> None:
        if self.baseline_policy_key not in self.runs:
            raise ValueError("support bake-off has no baseline run")
        if set(self.admissions) != set(self.runs) - {self.baseline_policy_key}:
            raise ValueError("support bake-off admissions differ from candidate runs")
        if any(not _SAFE_KEY.fullmatch(key) for key in self.runs):
            raise ValueError("support bake-off policy keys must be safe artifact names")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": BAKEOFF_SCHEMA,
            "plan": {"key": self.plan_key, "sha256": self.plan_sha256},
            "baseline_policy_key": self.baseline_policy_key,
            "runs": {
                key: run.sha256 for key, run in sorted(self.runs.items())
            },
            "admissions": {
                key: report.sha256
                for key, report in sorted(self.admissions.items())
            },
            "passed_candidates": sorted(
                key for key, report in self.admissions.items() if report.passed
            ),
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    def write(self, output_directory: str | Path) -> Path:
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        for key, run in sorted(self.runs.items()):
            (output / f"{key}.run.json").write_text(
                json.dumps(run.to_dict(), indent=2, sort_keys=True) + "\n"
            )
        for key, report in sorted(self.admissions.items()):
            (output / f"{key}.admission.json").write_text(
                json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
            )
        manifest = output / "bakeoff.json"
        manifest.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return manifest


def run_support_bakeoff(
    probe: SupportProbe,
    sources: Mapping[str, str],
    plan: SupportProbePlan,
    detectors: Mapping[str, SupportDetector],
    policies: Mapping[str, SupportPolicy],
) -> SupportBakeoff:
    """Execute the complete preregistered policy set without network access."""
    expected = set(plan.baseline_policy_keys) | set(plan.detector_policy_keys)
    if set(detectors) != expected or set(policies) != expected:
        raise ValueError("support bake-off components differ from frozen policy set")
    if len(plan.baseline_policy_keys) != 1:
        raise ValueError("support bake-off requires exactly one frozen baseline")
    runs = {}
    for key in sorted(expected):
        if policies[key].key != key:
            raise ValueError(f"support bake-off policy mapping key differs: {key}")
        runs[key] = run_support_probe(
            probe,
            sources,
            max_context_characters=plan.max_context_characters,
            detector=detectors[key],
            policy=policies[key],
            plan=plan,
        )
    baseline_key = plan.baseline_policy_keys[0]
    baseline = RecordedProbeRun.from_mapping(runs[baseline_key].to_dict())
    admissions = {
        key: evaluate_support_admission(
            plan,
            baseline,
            RecordedProbeRun.from_mapping(runs[key].to_dict()),
            probe=probe,
        )
        for key in sorted(plan.detector_policy_keys)
    }
    return SupportBakeoff(
        plan_key=plan.key,
        plan_sha256=plan.sha256,
        baseline_policy_key=baseline_key,
        runs=runs,
        admissions=admissions,
    )


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

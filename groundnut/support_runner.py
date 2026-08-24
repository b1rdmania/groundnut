"""Reproducible execution of paired support probes over frozen detectors."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .provenance import sha256_text
from .probe_plan import SupportProbePlan
from .sources import ResolvedSource, SourceReference, SourceResolution
from .support import (
    DETECTOR_LABELS,
    ClaimAssessment,
    DetectorIdentity,
    SupportDetector,
    SupportPolicy,
    assess_claim_support,
)
from .support_cases import SupportProbe, contexts_sha256
from .support_eval import SupportGold, score_support
from .verification import Claim, verify_claim


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProbeContextDigest:
    case_id: str
    sha256: str
    characters: int

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not _SHA256.fullmatch(self.sha256):
            raise ValueError("probe context requires case id and lowercase SHA-256")
        if self.characters < 1:
            raise ValueError("probe context must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "sha256": self.sha256,
            "characters": self.characters,
        }


@dataclass(frozen=True)
class SupportProbeRun:
    plan_key: str
    plan_sha256: str
    probe_sha256: str
    max_context_characters: int
    policy_key: str
    policy_sha256: str
    detector: DetectorIdentity
    contexts: tuple[ProbeContextDigest, ...]
    gold: tuple[SupportGold, ...]
    assessments: tuple[ClaimAssessment, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "contexts", tuple(sorted(self.contexts, key=lambda row: row.case_id))
        )
        object.__setattr__(
            self, "gold", tuple(sorted(self.gold, key=lambda row: row.case_id))
        )
        object.__setattr__(
            self,
            "assessments",
            tuple(sorted(self.assessments, key=lambda row: row.support.claim_id)),
        )
        if self.max_context_characters < 1:
            raise ValueError("probe context size must be positive")
        if not all(
            _SHA256.fullmatch(value)
            for value in (self.plan_sha256, self.probe_sha256, self.policy_sha256)
        ):
            raise ValueError("plan, probe, and policy hashes must be lowercase SHA-256")
        if not self.plan_key.strip() or not self.policy_key.strip():
            raise ValueError("probe run plan and policy keys are required")
        expected = [row.case_id for row in self.gold]
        contexts = [row.case_id for row in self.contexts]
        actual = [row.support.claim_id for row in self.assessments]
        if len(expected) != len(set(expected)):
            raise ValueError("probe run case ids must be unique")
        if expected != contexts or expected != actual:
            raise ValueError("probe gold, context, and assessment case ids must match")
        if any(
            row.support.policy_key != self.policy_key
            or row.support.policy_sha256 != self.policy_sha256
            or row.support.detector != self.detector
            for row in self.assessments
        ):
            raise ValueError("probe assessment identity differs from frozen run identity")
        context_by_id = {row.case_id: row.sha256 for row in self.contexts}
        if any(
            row.support.source_sha256 != context_by_id[row.support.claim_id]
            for row in self.assessments
        ):
            raise ValueError("probe assessment source hash differs from context hash")

    @property
    def complete(self) -> bool:
        return all(
            row.support.status in DETECTOR_LABELS for row in self.assessments
        )

    @property
    def score(self) -> dict[str, Any]:
        return score_support(
            self.gold, [row.support for row in self.assessments]
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-support-probe-run/v3",
            "plan": {"key": self.plan_key, "sha256": self.plan_sha256},
            "probe_sha256": self.probe_sha256,
            "max_context_characters": self.max_context_characters,
            "policy": {"key": self.policy_key, "sha256": self.policy_sha256},
            "detector": {
                **self.detector.canonical_payload(),
                "sha256": self.detector.sha256,
            },
            "complete": self.complete,
            "contexts": [row.to_dict() for row in self.contexts],
            "gold": [row.to_dict() for row in self.gold],
            "score": self.score,
            "assessments": [row.to_dict() for row in self.assessments],
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def run_support_probe(
    probe: SupportProbe,
    sources: Mapping[str, str],
    *,
    max_context_characters: int,
    detector: SupportDetector,
    policy: SupportPolicy,
    plan: SupportProbePlan,
) -> SupportProbeRun:
    """Run one frozen detector over source-identical paired probe windows."""
    plan.validate_probe(probe.sha256, probe.group_count)
    if max_context_characters != plan.max_context_characters:
        raise ValueError("probe context size differs from frozen plan")
    admitted_policies = set(plan.baseline_policy_keys) | set(plan.detector_policy_keys)
    if policy.key not in admitted_policies:
        raise ValueError(f"policy is not frozen in probe plan: {policy.key}")
    if policy.sha256 != plan.policy_sha256(policy.key):
        raise ValueError("support policy hash differs from frozen probe plan")
    contexts = probe.contexts(sources, max_context_characters)
    if contexts_sha256(contexts) != plan.contexts_sha256:
        raise ValueError("probe contexts differ from frozen plan")
    context_digests = []
    assessments = []
    for case in probe.cases:
        context = contexts[case.case_id]
        context_sha256 = sha256_text(context)
        reference = SourceReference(
            source_id=case.source_id,
            uri=f"groundnut-probe://{case.source_sha256}/{context_sha256}",
        )
        resolution = SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=context,
                fetched_at="frozen-probe-input",
                media_type="text/plain",
            )
        )
        claim = Claim(
            claim_id=case.case_id,
            text=case.claim_text,
            source=reference,
            question=case.question,
        )
        assessment = assess_claim_support(
            verify_claim(claim, resolution),
            resolution,
            detector=detector,
            policy=policy,
        )
        context_digests.append(
            ProbeContextDigest(
                case_id=case.case_id,
                sha256=context_sha256,
                characters=len(context),
            )
        )
        assessments.append(assessment)
    return SupportProbeRun(
        plan_key=plan.key,
        plan_sha256=plan.sha256,
        probe_sha256=probe.sha256,
        max_context_characters=max_context_characters,
        policy_key=policy.key,
        policy_sha256=policy.sha256,
        detector=detector.identity,
        contexts=tuple(context_digests),
        gold=probe.gold(),
        assessments=tuple(assessments),
    )

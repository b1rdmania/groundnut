"""Semantic claim-support contracts with immutable mechanical provenance.

Detectors answer whether a claim is supported by source text. They do not
rewrite source resolution, excerpt anchoring, or any other mechanical result.
Every assessment records the exact detector and frozen policy that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from .sources import SourceResolution
from .verification import Claim, VerifiedClaim, normalise


SUPPORT_POLICY_SCHEMA = "groundnut-support-policy/v1"
SUPPORT_STATUSES = {
    "supported",
    "contradicted",
    "insufficient",
    "source_unavailable",
    "not_assessed",
}
DETECTOR_LABELS = {"supported", "contradicted", "insufficient"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
EMPTY_CONFIGURATION_SHA256 = hashlib.sha256(b"{}").hexdigest()


def configuration_sha256(value: Mapping[str, Any]) -> str:
    """Hash adapter configuration without including credentials or secrets."""
    return _sha256_json(value)


@dataclass(frozen=True)
class DetectorIdentity:
    adapter: str
    model: str
    revision: str
    package: str
    package_version: str
    configuration_sha256: str = EMPTY_CONFIGURATION_SHA256

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.adapter,
                self.model,
                self.revision,
                self.package,
                self.package_version,
            )
        ):
            raise ValueError("detector identity fields must not be empty")
        if self.revision.casefold() in {"main", "master", "latest", "head"}:
            raise ValueError("detector revision must be immutable, not a moving ref")
        if not _SHA256.fullmatch(self.configuration_sha256):
            raise ValueError("detector configuration_sha256 must be lowercase SHA-256")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "adapter": self.adapter,
            "model": self.model,
            "revision": self.revision,
            "package": self.package,
            "package_version": self.package_version,
            "configuration_sha256": self.configuration_sha256,
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DetectorIdentity":
        return cls(
            adapter=str(value["adapter"]),
            model=str(value["model"]),
            revision=str(value["revision"]),
            package=str(value["package"]),
            package_version=str(value["package_version"]),
            configuration_sha256=str(
                value.get("configuration_sha256", EMPTY_CONFIGURATION_SHA256)
            ),
        )


@dataclass(frozen=True)
class SupportSpan:
    start: int
    end: int
    text: str
    label: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("support span offsets must describe a non-empty span")
        if not self.text or not self.label.strip():
            raise ValueError("support span text and label must not be empty")
        _require_confidence(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "label": self.label,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class DetectorDecision:
    label: str
    confidence: float | None
    reason: str
    spans: tuple[SupportSpan, ...] = field(default_factory=tuple)
    raw_output_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "spans", tuple(self.spans))
        if self.label not in DETECTOR_LABELS:
            raise ValueError(f"unknown detector label: {self.label}")
        _require_confidence(self.confidence)
        if not self.reason.strip():
            raise ValueError("detector decision reason must not be empty")
        if self.label == "supported" and self.spans:
            raise ValueError("supported decision cannot carry adverse spans")
        if self.raw_output_sha256 is not None and not _SHA256.fullmatch(
            self.raw_output_sha256
        ):
            raise ValueError("raw_output_sha256 must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "reason": self.reason,
            "spans": [span.to_dict() for span in self.spans],
            "raw_output_sha256": self.raw_output_sha256,
        }


class SupportDetector(Protocol):
    identity: DetectorIdentity

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision: ...


@dataclass(frozen=True)
class SupportPolicy:
    key: str
    version: str
    frozen_at: str
    detector: DetectorIdentity
    min_confidence: float | None
    schema: str = SUPPORT_POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SUPPORT_POLICY_SCHEMA:
            raise ValueError(f"unsupported support policy schema: {self.schema}")
        if (
            not self.key.strip()
            or not self.version.strip()
            or not self.frozen_at.strip()
        ):
            raise ValueError("support policy identity and frozen_at are required")
        _require_confidence(self.min_confidence)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "key": self.key,
            "version": self.version,
            "frozen_at": self.frozen_at,
            "detector": self.detector.canonical_payload(),
            "min_confidence": self.min_confidence,
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SupportPolicy":
        return cls(
            schema=str(value.get("schema", SUPPORT_POLICY_SCHEMA)),
            key=str(value["key"]),
            version=str(value["version"]),
            frozen_at=str(value["frozen_at"]),
            detector=DetectorIdentity.from_mapping(value["detector"]),
            min_confidence=(
                float(value["min_confidence"])
                if value.get("min_confidence") is not None
                else None
            ),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "SupportPolicy":
        return cls.from_mapping(json.loads(Path(path).read_text()))


@dataclass(frozen=True)
class SupportAssessment:
    claim_id: str
    status: str
    note: str
    source_sha256: str | None
    input_sha256: str
    policy_key: str
    policy_sha256: str
    detector: DetectorIdentity
    decision: DetectorDecision | None = None
    failure: str | None = None

    def __post_init__(self) -> None:
        if self.status not in SUPPORT_STATUSES:
            raise ValueError(f"unknown support status: {self.status}")
        if not self.claim_id.strip() or not self.note.strip():
            raise ValueError("support assessment claim_id and note are required")
        if self.status in DETECTOR_LABELS and self.decision is None:
            raise ValueError("semantic support status requires a detector decision")
        if self.status == "source_unavailable" and not self.failure:
            raise ValueError("source_unavailable assessment requires a failure")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-support-assessment/v1",
            "claim_id": self.claim_id,
            "status": self.status,
            "note": self.note,
            "source_sha256": self.source_sha256,
            "input_sha256": self.input_sha256,
            "policy": {"key": self.policy_key, "sha256": self.policy_sha256},
            "detector": {
                **self.detector.canonical_payload(),
                "sha256": self.detector.sha256,
            },
            "decision": self.decision.to_dict() if self.decision else None,
            "failure": self.failure,
        }


@dataclass(frozen=True)
class ClaimAssessment:
    """Mechanical verification and semantic support, preserved side by side."""

    verification: VerifiedClaim
    support: SupportAssessment

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-claim-assessment/v1",
            "verification": self.verification.to_dict(),
            "support": self.support.to_dict(),
        }


class ExactSupportDetector:
    """Deterministic normalized-substring baseline, not a semantic judge."""

    identity = DetectorIdentity(
        adapter="groundnut.exact",
        model="normalised_substring",
        revision="1",
        package="groundnut",
        package_version="1",
    )

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision:
        needle = normalise(claim_text)
        found = bool(needle) and needle in normalise(source_text)
        return DetectorDecision(
            label="supported" if found else "insufficient",
            confidence=1.0,
            reason=(
                "Normalized claim text occurs in the source."
                if found
                else "Normalized claim text does not occur in the source."
            ),
        )


def assess_claim_support(
    verification: VerifiedClaim,
    resolution: SourceResolution | None,
    *,
    detector: SupportDetector,
    policy: SupportPolicy,
) -> ClaimAssessment:
    """Assess support without mutating or upgrading mechanical verification."""
    claim = verification.claim
    if detector.identity != policy.detector:
        raise ValueError("detector identity does not match frozen support policy")
    source = resolution.source if resolution and resolution.ok else None
    source_sha256 = source.record.sha256 if source else None
    input_sha256 = _input_sha256(claim, source_sha256)

    def result(
        status: str,
        note: str,
        *,
        decision: DetectorDecision | None = None,
        failure: str | None = None,
    ) -> ClaimAssessment:
        return ClaimAssessment(
            verification=verification,
            support=SupportAssessment(
                claim_id=claim.claim_id,
                status=status,
                note=note,
                source_sha256=source_sha256,
                input_sha256=input_sha256,
                policy_key=policy.key,
                policy_sha256=policy.sha256,
                detector=detector.identity,
                decision=decision,
                failure=failure,
            ),
        )

    if claim.source is None:
        return result(
            "not_assessed",
            "Claim has no external source; semantic support was not assessed.",
            failure="no_source",
        )
    if source is None:
        failure = resolution.failure if resolution else "source_unreachable"
        return result(
            "source_unavailable",
            "Source was unavailable; no semantic support verdict was produced.",
            failure=failure,
        )
    if source.reference != claim.source:
        return result(
            "source_unavailable",
            "Resolved source identity differs from the claim citation.",
            failure="source_changed",
        )
    try:
        decision = detector.assess(
            source_text=source.text,
            claim_text=claim.text,
            question=claim.question,
        )
        _validate_spans(decision.spans, claim.text)
    except Exception as error:
        return result(
            "not_assessed",
            "Detector failed; mechanical verification is preserved unchanged.",
            failure=f"detector_error:{type(error).__name__}",
        )
    if policy.min_confidence is not None and (
        decision.confidence is None or decision.confidence < policy.min_confidence
    ):
        return result(
            "insufficient",
            "Detector confidence did not meet the frozen policy threshold.",
            decision=decision,
        )
    return result(
        decision.label,
        "Semantic support assessment completed under the frozen policy.",
        decision=decision,
    )


def _validate_spans(spans: tuple[SupportSpan, ...], claim_text: str) -> None:
    for span in spans:
        if span.end > len(claim_text) or claim_text[span.start : span.end] != span.text:
            raise ValueError("detector span does not match claim text at its offsets")


def _input_sha256(claim: Claim, source_sha256: str | None) -> str:
    return _sha256_json(
        {
            "claim_text": claim.text,
            "question": claim.question,
            "source_sha256": source_sha256,
        }
    )


def _require_confidence(value: float | None) -> None:
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

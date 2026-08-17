"""End-to-end, fail-closed claim checking over Groundnut primitives."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .sources import SourceReference, SourceResolution
from .support import (
    DETECTOR_LABELS,
    SUPPORT_STATUSES,
    ClaimAssessment,
    SupportDetector,
    SupportPolicy,
    assess_claim_support,
)
from .verification import Claim, verification_metrics, verify_claim


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ClaimCheckReport:
    policy_key: str
    policy_sha256: str
    claims: tuple[ClaimAssessment, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "claims", tuple(sorted(self.claims, key=lambda row: row.support.claim_id))
        )
        if not self.policy_key.strip():
            raise ValueError("claim-check report policy key is required")
        if not _SHA256.fullmatch(self.policy_sha256):
            raise ValueError("claim-check policy hash must be lowercase SHA-256")
        if not self.claims:
            raise ValueError("claim-check report requires at least one claim")
        claim_ids = [row.support.claim_id for row in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("duplicate claim id in claim-check report")
        if any(
            row.verification.claim.claim_id != row.support.claim_id
            for row in self.claims
        ):
            raise ValueError("mechanical and semantic claim identities differ")
        if any(
            row.support.policy_key != self.policy_key
            or row.support.policy_sha256 != self.policy_sha256
            for row in self.claims
        ):
            raise ValueError("claim support policy differs from report policy")

    @property
    def complete(self) -> bool:
        return all(row.support.status in DETECTOR_LABELS for row in self.claims)

    @property
    def summary(self) -> dict[str, Any]:
        statuses = {status: 0 for status in sorted(SUPPORT_STATUSES)}
        for row in self.claims:
            statuses[row.support.status] += 1
        return {
            "claims": len(self.claims),
            "support_status_counts": statuses,
            "semantic_assessments": sum(
                statuses[status] for status in DETECTOR_LABELS
            ),
            "unresolved_assessments": sum(
                statuses[status]
                for status in {"source_unavailable", "not_assessed"}
            ),
            "mechanical": verification_metrics(
                [row.verification for row in self.claims]
            ),
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-claim-check-report/v1",
            "policy": {"key": self.policy_key, "sha256": self.policy_sha256},
            "complete": self.complete,
            "summary": self.summary,
            "claims": [row.to_dict() for row in self.claims],
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


def check_claims(
    claims: Iterable[Claim],
    resolutions: Mapping[SourceReference, SourceResolution],
    *,
    detector: SupportDetector,
    policy: SupportPolicy,
) -> ClaimCheckReport:
    """Check a claim batch while preserving every mechanical result."""
    claims = tuple(claims)
    if not claims:
        raise ValueError("claim checker requires at least one claim")
    claim_ids = [claim.claim_id for claim in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("duplicate claim id in claim-check input")

    rows = []
    for claim in claims:
        resolution = resolutions.get(claim.source) if claim.source else None
        mechanical = verify_claim(claim, resolution)
        rows.append(
            assess_claim_support(
                mechanical,
                resolution,
                detector=detector,
                policy=policy,
            )
        )

    rows = sorted(rows, key=lambda row: row.support.claim_id)
    return ClaimCheckReport(
        policy_key=policy.key,
        policy_sha256=policy.sha256,
        claims=tuple(rows),
    )

"""Evidence-authority contracts kept independent from semantic support."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .checker import ClaimCheckReport
from .support import ClaimAssessment


AUTHORITY_SCHEMA = "groundnut-evidence-authority/v1"
AUTHORITY_KINDS = {
    "independent_primary",
    "independent_secondary",
    "subject_provided",
    "analyst_derived",
    "unknown_authority",
}
ASSIGNMENT_BASES = {
    "source_metadata",
    "human_adjudication",
    "domain_policy",
    "artifact_declaration",
    "unassigned",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AuthorityPolicy:
    key: str
    version: str
    frozen_at: str
    kinds: tuple[str, ...] = tuple(sorted(AUTHORITY_KINDS))
    schema: str = "groundnut-authority-policy/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "kinds", tuple(sorted(self.kinds)))
        if self.schema != "groundnut-authority-policy/v1":
            raise ValueError(f"unsupported authority policy schema: {self.schema}")
        if not self.key.strip() or not self.version.strip() or not self.frozen_at.strip():
            raise ValueError("authority policy identity and frozen_at are required")
        if set(self.kinds) != AUTHORITY_KINDS or len(self.kinds) != len(AUTHORITY_KINDS):
            raise ValueError("authority policy must retain the complete canonical vocabulary")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "key": self.key,
            "version": self.version,
            "frozen_at": self.frozen_at,
            "kinds": list(self.kinds),
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AuthorityPolicy":
        return cls(
            schema=str(value.get("schema", "groundnut-authority-policy/v1")),
            key=str(value["key"]),
            version=str(value["version"]),
            frozen_at=str(value["frozen_at"]),
            kinds=tuple(str(item) for item in value.get("kinds", AUTHORITY_KINDS)),
        )


@dataclass(frozen=True)
class AuthorityDeclaration:
    kind: str
    basis: str
    assigned_by: str
    note: str
    source_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in AUTHORITY_KINDS - {"unknown_authority"}:
            raise ValueError("authority declarations require a known canonical kind")
        if self.basis not in ASSIGNMENT_BASES - {"unassigned", "artifact_declaration"}:
            raise ValueError("authority declaration basis must be independently auditable")
        if not self.assigned_by.strip() or not self.note.strip():
            raise ValueError("authority declaration requires assigner and note")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "basis": self.basis,
            "assigned_by": self.assigned_by,
            "note": self.note,
            "source_id": self.source_id,
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AuthorityDeclaration":
        return cls(
            kind=str(value["kind"]),
            basis=str(value["basis"]),
            assigned_by=str(value["assigned_by"]),
            note=str(value["note"]),
            source_id=str(value["source_id"]) if value.get("source_id") else None,
        )


@dataclass(frozen=True)
class AuthorityAssessment:
    claim_id: str
    source_id: str | None
    kind: str
    basis: str
    assigned_by: str | None
    note: str
    policy_key: str
    policy_sha256: str
    declaration_sha256: str | None
    support_input_sha256: str
    schema: str = AUTHORITY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != AUTHORITY_SCHEMA:
            raise ValueError(f"unsupported evidence-authority schema: {self.schema}")
        if self.kind not in AUTHORITY_KINDS or self.basis not in ASSIGNMENT_BASES:
            raise ValueError("unknown evidence authority kind or basis")
        if not self.claim_id.strip() or not self.note.strip() or not self.policy_key.strip():
            raise ValueError("evidence-authority identity and note are required")
        for value in (self.policy_sha256, self.support_input_sha256):
            if not _SHA256.fullmatch(value):
                raise ValueError("evidence-authority hashes must be lowercase SHA-256")
        if self.declaration_sha256 is not None and not _SHA256.fullmatch(
            self.declaration_sha256
        ):
            raise ValueError("authority declaration hash must be lowercase SHA-256")
        if self.kind == "unknown_authority" and (
            self.basis != "unassigned"
            or self.assigned_by is not None
            or self.declaration_sha256 is not None
        ):
            raise ValueError("unknown authority must remain explicitly unassigned")
        if self.kind != "unknown_authority" and self.basis == "unassigned":
            raise ValueError("known authority cannot use an unassigned basis")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "claim_id": self.claim_id,
            "source_id": self.source_id,
            "kind": self.kind,
            "basis": self.basis,
            "assigned_by": self.assigned_by,
            "note": self.note,
            "policy": {"key": self.policy_key, "sha256": self.policy_sha256},
            "declaration_sha256": self.declaration_sha256,
            "support_input_sha256": self.support_input_sha256,
        }


@dataclass(frozen=True)
class ClaimEvidenceAccount:
    assessment: ClaimAssessment
    authority: AuthorityAssessment

    def __post_init__(self) -> None:
        if self.assessment.support.claim_id != self.authority.claim_id:
            raise ValueError("support and authority claim identities differ")
        source = self.assessment.verification.claim.source
        if (source.source_id if source else None) != self.authority.source_id:
            raise ValueError("support and authority source identities differ")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-claim-evidence-account/v1",
            "assessment": self.assessment.to_dict(),
            "authority": self.authority.to_dict(),
        }


@dataclass(frozen=True)
class ClaimEvidenceReport:
    support_policy_key: str
    support_policy_sha256: str
    authority_policy_key: str
    authority_policy_sha256: str
    accounts: tuple[ClaimEvidenceAccount, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "accounts",
            tuple(sorted(self.accounts, key=lambda row: row.authority.claim_id)),
        )
        if not self.accounts:
            raise ValueError("claim evidence report requires at least one account")
        claim_ids = [row.authority.claim_id for row in self.accounts]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("duplicate claim id in claim evidence report")

    @property
    def complete_authority(self) -> bool:
        return all(
            row.authority.kind != "unknown_authority" for row in self.accounts
        )

    def canonical_payload(self) -> dict[str, Any]:
        authority_counts = {kind: 0 for kind in sorted(AUTHORITY_KINDS)}
        support_counts: dict[str, int] = {}
        for row in self.accounts:
            authority_counts[row.authority.kind] += 1
            status = row.assessment.support.status
            support_counts[status] = support_counts.get(status, 0) + 1
        return {
            "schema": "groundnut-claim-evidence-report/v1",
            "support_policy": {
                "key": self.support_policy_key,
                "sha256": self.support_policy_sha256,
            },
            "authority_policy": {
                "key": self.authority_policy_key,
                "sha256": self.authority_policy_sha256,
            },
            "complete_authority": self.complete_authority,
            "summary": {
                "claims": len(self.accounts),
                "support_status_counts": dict(sorted(support_counts.items())),
                "authority_kind_counts": authority_counts,
            },
            "accounts": [row.to_dict() for row in self.accounts],
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def assess_evidence_authority(
    assessment: ClaimAssessment,
    *,
    policy: AuthorityPolicy,
    declaration: AuthorityDeclaration | None = None,
) -> ClaimEvidenceAccount:
    claim = assessment.verification.claim
    source_id = claim.source.source_id if claim.source else None
    if declaration is not None and declaration.source_id != source_id:
        raise ValueError("authority declaration source does not match claim source")

    if declaration is not None:
        kind = declaration.kind
        basis = declaration.basis
        assigned_by = declaration.assigned_by
        note = declaration.note
        declaration_sha256 = declaration.sha256
    elif claim.declared_analysis:
        kind = "analyst_derived"
        basis = "artifact_declaration"
        assigned_by = None
        note = "Artifact explicitly declares analyst-derived analysis."
        declaration_sha256 = None
    else:
        kind = "unknown_authority"
        basis = "unassigned"
        assigned_by = None
        note = "No evidence-authority declaration was supplied."
        declaration_sha256 = None

    authority = AuthorityAssessment(
        claim_id=claim.claim_id,
        source_id=source_id,
        kind=kind,
        basis=basis,
        assigned_by=assigned_by,
        note=note,
        policy_key=policy.key,
        policy_sha256=policy.sha256,
        declaration_sha256=declaration_sha256,
        support_input_sha256=assessment.support.input_sha256,
    )
    return ClaimEvidenceAccount(assessment=assessment, authority=authority)


def account_for_claim_check(
    report: ClaimCheckReport,
    *,
    policy: AuthorityPolicy,
    declarations: Mapping[str, AuthorityDeclaration] | None = None,
) -> ClaimEvidenceReport:
    declarations = declarations or {}
    known = {row.support.claim_id for row in report.claims}
    extras = set(declarations) - known
    if extras:
        raise ValueError(f"authority declarations reference unknown claims: {sorted(extras)}")
    accounts = tuple(
        assess_evidence_authority(
            row,
            policy=policy,
            declaration=declarations.get(row.support.claim_id),
        )
        for row in report.claims
    )
    return ClaimEvidenceReport(
        support_policy_key=report.policy_key,
        support_policy_sha256=report.policy_sha256,
        authority_policy_key=policy.key,
        authority_policy_sha256=policy.sha256,
        accounts=accounts,
    )


def _sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

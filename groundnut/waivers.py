"""Human waiver contract for an otherwise failing Groundnut gate."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping


WAIVER_SCHEMA = "groundnut-gate-waiver/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class GateWaiver:
    gate: str
    artifact_sha256: str
    ledger_sha256: str
    approved_by: str
    approved_at: str
    reason: str
    waived_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "waived_unit_ids", tuple(sorted(self.waived_unit_ids)))
        if self.gate != "undeclared_numeric_own_reasoning":
            raise ValueError(f"unsupported waiver gate: {self.gate}")
        if not _SHA256.fullmatch(self.artifact_sha256):
            raise ValueError("waiver artifact_sha256 must be lowercase SHA-256")
        if not _SHA256.fullmatch(self.ledger_sha256):
            raise ValueError("waiver ledger_sha256 must be lowercase SHA-256")
        if not self.approved_by.startswith("human:") or len(self.approved_by) <= 6:
            raise ValueError("waiver approved_by must name a human: reviewer")
        if not self.approved_at.strip() or not self.reason.strip():
            raise ValueError("waiver requires approved_at and reason")
        if not self.waived_unit_ids:
            raise ValueError("waiver requires at least one unit id")
        if len(set(self.waived_unit_ids)) != len(self.waived_unit_ids):
            raise ValueError("waiver unit ids must be unique")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": WAIVER_SCHEMA,
            "gate": self.gate,
            "artifact_sha256": self.artifact_sha256,
            "ledger_sha256": self.ledger_sha256,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "reason": self.reason,
            "waived_unit_ids": list(self.waived_unit_ids),
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GateWaiver":
        if value.get("schema") != WAIVER_SCHEMA:
            raise ValueError(f"unsupported waiver schema: {value.get('schema')!r}")
        unit_ids = value.get("waived_unit_ids")
        if not isinstance(unit_ids, list):
            raise ValueError("waived_unit_ids must be an array")
        waiver = cls(
            gate=str(value.get("gate", "")),
            artifact_sha256=str(value.get("artifact_sha256", "")),
            ledger_sha256=str(value.get("ledger_sha256", "")),
            approved_by=str(value.get("approved_by", "")),
            approved_at=str(value.get("approved_at", "")),
            reason=str(value.get("reason", "")),
            waived_unit_ids=tuple(str(item) for item in unit_ids),
        )
        supplied = value.get("sha256")
        if supplied is not None and supplied != waiver.sha256:
            raise ValueError("waiver sha256 does not match its canonical payload")
        return waiver


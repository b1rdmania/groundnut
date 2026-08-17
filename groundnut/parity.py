"""Frozen semantic projection for deployment-to-Groundnut parity checks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


PARITY_SCHEMA = "groundnut-analysis-parity/v1"


@dataclass(frozen=True)
class ParityExclusion:
    path: str
    reason: str

    def __post_init__(self) -> None:
        if not self.path.startswith("/") or not self.reason.strip():
            raise ValueError("parity exclusion requires a JSON path and reason")

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}


EXCLUSIONS = (
    ParityExclusion(
        "/domain/evidence_disclosure",
        "Quality disclosure is Groundnut metadata absent from the legacy result; "
        "it does not change the executable playbook.",
    ),
    ParityExclusion(
        "/domain/evidence_status",
        "Evidence maturity is Groundnut metadata absent from the legacy result; "
        "it is evaluated separately from output parity.",
    ),
    ParityExclusion(
        "/domain/manifest_sha256",
        "The manifest includes Groundnut-only evidence metadata; executable job "
        "identity remains compared through playbook_sha256.",
    ),
    ParityExclusion(
        "/source/source_id",
        "Source IDs are host-local; source content hash and character count remain "
        "inside the parity projection.",
    ),
    ParityExclusion(
        "/anchored_findings/*/anchor/source_id",
        "Anchor source IDs repeat the same host-local identifier; source hash, "
        "quote, match mode, and offsets remain compared.",
    ),
)
EXCLUDED_PATHS = tuple(row.path for row in EXCLUSIONS)


def _exclusion_contract_sha256() -> str:
    encoded = json.dumps(
        [row.to_dict() for row in EXCLUSIONS],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


EXCLUSION_CONTRACT_SHA256 = _exclusion_contract_sha256()
PINNED_EXCLUSION_CONTRACT_SHA256 = (
    "7c568a1c85d0d82b56d9956933eaa5a2e7c8e2dad176634209b56ce7c2014141"
)
if EXCLUSION_CONTRACT_SHA256 != PINNED_EXCLUSION_CONTRACT_SHA256:
    raise RuntimeError(
        "parity exclusions changed without updating the reviewed contract hash"
    )


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unknown:
            details.append(f"unknown {unknown}")
        raise ValueError(f"parity schema mismatch at {path}: {'; '.join(details)}")


def semantic_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    """Select fields that must remain equivalent across host implementations.

    The exclusions are metadata absent from the legacy deployment result or
    intentionally host-local. They are named in ``EXCLUDED_PATHS`` and in the
    parity report rather than being implicit comparator behaviour.
    """
    _require_exact_keys(
        value,
        {
            "schema",
            "domain",
            "source",
            "segments_total",
            "coverage",
            "findings",
            "anchored_findings",
        },
        "/",
    )
    if value["schema"] != "groundnut-analysis/v1":
        raise ValueError(f"unsupported analysis schema: {value['schema']}")
    domain = value["domain"]
    source = value["source"]
    anchored = value["anchored_findings"]
    _require_exact_keys(
        domain,
        {
            "key",
            "version",
            "playbook_sha256",
            "manifest_sha256",
            "evidence_status",
            "evidence_disclosure",
        },
        "/domain",
    )
    _require_exact_keys(source, {"source_id", "sha256", "characters"}, "/source")
    for index, row in enumerate(anchored):
        _require_exact_keys(
            row,
            {"category_key", "category_name", "severity", "quote", "anchor"},
            f"/anchored_findings/{index}",
        )
        _require_exact_keys(
            row["anchor"],
            {"source_id", "source_sha256", "quote", "exact", "normalised", "offsets"},
            f"/anchored_findings/{index}/anchor",
        )
    return {
        "schema": PARITY_SCHEMA,
        "domain": {
            "key": domain["key"],
            "version": domain["version"],
            "playbook_sha256": domain["playbook_sha256"],
        },
        "source": {
            "sha256": source["sha256"],
            "characters": source["characters"],
        },
        "segments_total": value["segments_total"],
        "coverage": value["coverage"],
        "findings": value["findings"],
        "anchored_findings": [
            {
                "category_key": row["category_key"],
                "category_name": row["category_name"],
                "severity": row["severity"],
                "quote": row["quote"],
                "anchor": {
                    "source_sha256": row["anchor"]["source_sha256"],
                    "quote": row["anchor"]["quote"],
                    "exact": row["anchor"]["exact"],
                    "normalised": row["anchor"]["normalised"],
                    "offsets": row["anchor"]["offsets"],
                },
            }
            for row in anchored
        ],
    }


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        semantic_projection(value), sort_keys=True, separators=(",", ":")
    ).encode()


@dataclass(frozen=True)
class ParityComparison:
    equal: bool
    expected_sha256: str
    actual_sha256: str

    @property
    def excluded_paths(self) -> tuple[str, ...]:
        return EXCLUDED_PATHS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-parity-comparison/v1",
            "equal": self.equal,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "excluded_paths": list(self.excluded_paths),
            "exclusion_contract_sha256": EXCLUSION_CONTRACT_SHA256,
            "exclusions": [row.to_dict() for row in EXCLUSIONS],
        }


def compare_analysis(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> ParityComparison:
    expected_bytes = canonical_bytes(expected)
    actual_bytes = canonical_bytes(actual)
    return ParityComparison(
        equal=expected_bytes == actual_bytes,
        expected_sha256=hashlib.sha256(expected_bytes).hexdigest(),
        actual_sha256=hashlib.sha256(actual_bytes).hexdigest(),
    )

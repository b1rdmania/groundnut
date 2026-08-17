"""Frozen semantic projection for deployment-to-Groundnut parity checks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


PARITY_SCHEMA = "groundnut-analysis-parity/v1"
EXCLUDED_PATHS = (
    "/domain/evidence_disclosure",
    "/domain/evidence_status",
    "/domain/manifest_sha256",
    "/source/source_id",
    "/anchored_findings/*/anchor/source_id",
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
    excluded_paths: tuple[str, ...] = EXCLUDED_PATHS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-parity-comparison/v1",
            "equal": self.equal,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "excluded_paths": list(self.excluded_paths),
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

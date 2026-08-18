"""Unlabelled relevance score envelopes for real claim/excerpt populations."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from .relevance_exploration import RelevanceScorer


RELEVANCE_ENVELOPE_SCHEMA = "groundnut-relevance-envelope/v1"


def run_relevance_envelope(
    cases: Iterable[Mapping[str, str]], scorer: RelevanceScorer
) -> dict[str, Any]:
    """Observe score distributions without manufacturing relevance labels."""
    rows = []
    seen = set()
    for case in cases:
        case_id = str(case["case_id"])
        if not case_id or case_id in seen:
            raise ValueError("relevance envelope case ids must be non-empty and unique")
        seen.add(case_id)
        query = str(case["query_text"])
        evidence = str(case["evidence_text"])
        stratum = str(case["stratum"])
        if not query.strip() or not evidence.strip() or not stratum.strip():
            raise ValueError("relevance envelope cases require query, evidence and stratum")
        signal = scorer.score(question=query, evidence_text=evidence)
        rows.append(
            {
                "case_id": case_id,
                "stratum": stratum,
                "query_sha256": _sha256_text(query),
                "evidence_sha256": _sha256_text(evidence),
                "relevance_score": signal.scores["relevant"],
                "component_signal": signal.to_dict(),
            }
        )
    if not rows:
        raise ValueError("relevance envelope requires cases")
    ordered = sorted(rows, key=lambda row: row["case_id"])
    payload = {
        "schema": RELEVANCE_ENVELOPE_SCHEMA,
        "qualification": "unlabelled_observation_only",
        "eligible_for_admission": False,
        "disclosure": (
            "This receipt contains no relevance gold. Strata describe an existing "
            "mechanical process and are not semantic labels. Score differences cannot "
            "qualify, tune, or threshold a component."
        ),
        "case_count": len(ordered),
        "summary": {
            stratum: _summary(
                [row["relevance_score"] for row in ordered if row["stratum"] == stratum]
            )
            for stratum in sorted({row["stratum"] for row in ordered})
        },
        "rows": ordered,
    }
    return {**payload, "sha256": _sha256_json(payload)}


def _summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "median": _quantile(ordered, 0.5),
        "mean": sum(ordered) / len(ordered),
        "maximum": ordered[-1],
    }


def _quantile(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

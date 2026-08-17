"""Deterministic scoring for frozen semantic-support development sets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .support import SUPPORT_STATUSES, SupportAssessment


@dataclass(frozen=True)
class SupportGold:
    case_id: str
    expected_status: str
    kind: str

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.kind.strip():
            raise ValueError("support gold case_id and kind are required")
        if self.expected_status not in SUPPORT_STATUSES:
            raise ValueError(
                f"unknown expected support status: {self.expected_status}"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "expected_status": self.expected_status,
            "kind": self.kind,
        }


def score_support(
    gold: Iterable[SupportGold], predictions: Iterable[SupportAssessment]
) -> dict[str, Any]:
    gold = tuple(gold)
    predictions = tuple(predictions)
    _require_unique("gold", [row.case_id for row in gold])
    _require_unique("prediction", [row.claim_id for row in predictions])
    gold_ids = {row.case_id for row in gold}
    extras = sorted(row.claim_id for row in predictions if row.claim_id not in gold_ids)
    if extras:
        raise ValueError(f"predictions contain unknown case ids: {extras}")

    by_id = {row.claim_id: row.status for row in predictions}
    labels = sorted({row.expected_status for row in gold})
    confusion: dict[str, dict[str, int]] = {
        expected: {actual: 0 for actual in sorted(SUPPORT_STATUSES | {"missing"})}
        for expected in labels
    }
    by_kind: dict[str, dict[str, int]] = {}
    correct = 0
    for row in gold:
        actual = by_id.get(row.case_id, "missing")
        confusion[row.expected_status][actual] += 1
        correct += actual == row.expected_status
        kind = by_kind.setdefault(row.kind, {"total": 0, "correct": 0})
        kind["total"] += 1
        kind["correct"] += actual == row.expected_status

    per_status = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_negative = sum(confusion[label].values()) - true_positive
        false_positive = sum(
            confusion[other][label] for other in labels if other != label
        )
        precision = _ratio(true_positive, true_positive + false_positive)
        recall = _ratio(true_positive, true_positive + false_negative)
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else 0.0
        )
        per_status[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(confusion[label].values()),
        }

    return {
        "schema": "groundnut-support-score/v1",
        "total": len(gold),
        "predicted": len(predictions),
        "missing": len(gold) - len(predictions),
        "accuracy": _ratio(correct, len(gold)),
        "macro_f1": (
            sum(row["f1"] for row in per_status.values()) / len(per_status)
            if per_status
            else None
        ),
        "per_status": per_status,
        "by_kind": {
            kind: {**counts, "accuracy": _ratio(counts["correct"], counts["total"])}
            for kind, counts in sorted(by_kind.items())
        },
        "confusion": confusion,
    }


def _require_unique(label: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} case id")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None

"""Question-to-evidence relevance exploration, separate from claim support."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping, Protocol

from .receipt import sha256_json as _sha256_json
from .signals import ComponentSignal
from .support_agent_screen import AgentSuggestion, screen_agent_suggestions
from .support_review import PilotReviewManifest


RELEVANCE_EXPLORATION_SCHEMA = "groundnut-relevance-exploration/v1"


class RelevanceScorer(Protocol):
    def score(
        self, *, question: str, evidence_text: str, claim_text: str = ""
    ) -> ComponentSignal: ...


def run_relevance_exploration(
    manifest: PilotReviewManifest,
    suggestions: Iterable[AgentSuggestion],
    scorer: RelevanceScorer,
) -> dict[str, Any]:
    """Score relevance without asking whether the evidence is true or supportive."""
    suggestion_rows = tuple(suggestions)
    by_hash = {row.input_sha256: row for row in suggestion_rows}
    screen = screen_agent_suggestions(manifest, suggestion_rows)
    included = set(screen.included_input_sha256)
    rows = []
    for review in manifest.rows[: manifest.target_group_count]:
        if review.input_sha256 not in included:
            continue
        suggestion = by_hash[review.input_sha256]
        cases = (
            ("verbatim_supported", True, review.candidate.original_text),
            ("paraphrase_supported", True, suggestion.paraphrase_text),
            ("contradicted", True, review.contradiction_text),
            ("present_irrelevant", False, review.candidate.claim_text),
        )
        for kind, expected_relevant, evidence_text in cases:
            case_id = hashlib.sha256(
                f"{review.input_sha256}:{kind}".encode()
            ).hexdigest()[:24]
            signal = scorer.score(
                question=review.candidate.question,
                evidence_text=evidence_text,
            )
            if signal.role != "relevance" or "relevant" not in signal.scores:
                raise ValueError("relevance scorer must emit a named relevance score")
            rows.append(
                {
                    "case_id": case_id,
                    "input_sha256": review.input_sha256,
                    "kind": kind,
                    "expected_relevant": expected_relevant,
                    "question_sha256": _sha256_text(review.candidate.question),
                    "evidence_sha256": _sha256_text(evidence_text),
                    "relevance_score": signal.scores["relevant"],
                    "component_signal": signal.to_dict(),
                }
            )
    ordered = sorted(rows, key=lambda row: row["case_id"])
    positive = [row for row in ordered if row["expected_relevant"]]
    negative = [row for row in ordered if not row["expected_relevant"]]
    payload = {
        "schema": RELEVANCE_EXPLORATION_SCHEMA,
        "qualification": "exploratory_only",
        "eligible_for_admission": False,
        "disclosure": (
            "Agent-screened development material. Relevance is measured separately "
            "from support and contradiction. This run cannot qualify a component."
        ),
        "screen_sha256": screen.sha256,
        "review_manifest_sha256": manifest.sha256,
        "group_count": len(included),
        "case_count": len(ordered),
        "relevant_case_count": len(positive),
        "irrelevant_case_count": len(negative),
        "metrics": {
            "roc_auc": _roc_auc(ordered),
            "average_precision": _average_precision(ordered),
            "mean_relevant_score": _mean(row["relevance_score"] for row in positive),
            "mean_irrelevant_score": _mean(row["relevance_score"] for row in negative),
            "paired_group_ranking": _paired_group_ranking(ordered),
            "by_kind": {
                kind: {
                    "count": sum(row["kind"] == kind for row in ordered),
                    "mean_relevance_score": _mean(
                        row["relevance_score"] for row in ordered if row["kind"] == kind
                    ),
                }
                for kind in sorted({row["kind"] for row in ordered})
            },
        },
        "rows": ordered,
    }
    return {**payload, "sha256": _sha256_json(payload)}


def validate_relevance_exploration(value: Mapping[str, Any]) -> None:
    if value.get("schema") != RELEVANCE_EXPLORATION_SCHEMA:
        raise ValueError("unsupported relevance exploration schema")
    supplied = str(value.get("sha256", ""))
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if supplied != _sha256_json(payload):
        raise ValueError("relevance exploration self-hash mismatch")
    if value.get("eligible_for_admission") is not False:
        raise ValueError("exploration cannot be eligible for admission")


def _roc_auc(rows: list[Mapping[str, Any]]) -> float:
    positive = [row["relevance_score"] for row in rows if row["expected_relevant"]]
    negative = [row["relevance_score"] for row in rows if not row["expected_relevant"]]
    if not positive or not negative:
        raise ValueError("ROC AUC requires both relevance classes")
    wins = sum(
        1.0 if left > right else 0.5 if left == right else 0.0
        for left in positive
        for right in negative
    )
    return wins / (len(positive) * len(negative))


def _average_precision(rows: list[Mapping[str, Any]]) -> float:
    ordered = sorted(rows, key=lambda row: (-row["relevance_score"], row["case_id"]))
    positives = sum(row["expected_relevant"] for row in ordered)
    if not positives:
        raise ValueError("average precision requires relevant cases")
    found = 0
    precision_sum = 0.0
    for rank, row in enumerate(ordered, start=1):
        if row["expected_relevant"]:
            found += 1
            precision_sum += found / rank
    return precision_sum / positives


def _mean(values: Iterable[float]) -> float:
    rows = tuple(values)
    if not rows:
        raise ValueError("mean requires at least one value")
    return sum(rows) / len(rows)


def _paired_group_ranking(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, float]] = {}
    for row in rows:
        groups.setdefault(str(row["input_sha256"]), {})[str(row["kind"])] = float(
            row["relevance_score"]
        )
    relevant_kinds = ("verbatim_supported", "paraphrase_supported", "contradicted")
    pairwise = {kind: 0.0 for kind in relevant_kinds}
    all_above = 0
    for scores in groups.values():
        if set(scores) != {*relevant_kinds, "present_irrelevant"}:
            raise ValueError("relevance exploration group is incomplete")
        irrelevant = scores["present_irrelevant"]
        comparisons = []
        for kind in relevant_kinds:
            value = 1.0 if scores[kind] > irrelevant else 0.5 if scores[kind] == irrelevant else 0.0
            pairwise[kind] += value
            comparisons.append(value)
        all_above += all(value == 1.0 for value in comparisons)
    count = len(groups)
    return {
        "group_count": count,
        "all_three_relevant_above_irrelevant_count": all_above,
        "all_three_relevant_above_irrelevant_rate": all_above / count,
        "pairwise_win_rate": {
            kind: wins / count for kind, wins in pairwise.items()
        },
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

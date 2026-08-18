"""Non-admissible execution over agent-screened semantic-support cases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from .provenance import sha256_text
from .support import SupportDetector
from .support_agent_screen import AgentSuggestion, screen_agent_suggestions
from .support_eval import SupportGold, score_support
from .support_review import PilotReviewManifest


EXPLORATION_SCHEMA = "groundnut-support-agent-exploration/v1"
COMPARISON_SCHEMA = "groundnut-support-agent-comparison/v1"


@dataclass(frozen=True)
class _Prediction:
    claim_id: str
    status: str


def run_agent_exploration(
    manifest: PilotReviewManifest,
    suggestions: Iterable[AgentSuggestion],
    detector: SupportDetector,
) -> dict[str, Any]:
    """Run a detector without creating a gold probe or admission decision."""
    suggestion_rows = tuple(suggestions)
    by_hash = {row.input_sha256: row for row in suggestion_rows}
    screen = screen_agent_suggestions(manifest, suggestion_rows)
    included = set(screen.included_input_sha256)
    gold = []
    predictions = []
    rows = []
    for review in manifest.rows[: manifest.target_group_count]:
        if review.input_sha256 not in included:
            continue
        suggestion = by_hash[review.input_sha256]
        cases = (
            ("verbatim_supported", "supported", review.candidate.original_text),
            ("paraphrase_supported", "supported", suggestion.paraphrase_text),
            ("contradicted", "contradicted", review.contradiction_text),
            ("present_irrelevant", "insufficient", review.candidate.claim_text),
        )
        for kind, expected, claim in cases:
            case_id = hashlib.sha256(
                f"{review.input_sha256}:{kind}".encode()
            ).hexdigest()[:24]
            assess_with_signal = getattr(detector, "assess_with_signal", None)
            signal = None
            if callable(assess_with_signal):
                decision, signal = assess_with_signal(
                    source_text=review.context_text,
                    claim_text=claim,
                    question=review.candidate.question,
                )
            else:
                decision = detector.assess(
                    source_text=review.context_text,
                    claim_text=claim,
                    question=review.candidate.question,
                )
            gold.append(SupportGold(case_id, expected, kind))
            predictions.append(_Prediction(case_id, decision.label))
            row = {
                "case_id": case_id,
                "input_sha256": review.input_sha256,
                "kind": kind,
                "expected_status": expected,
                "actual_status": decision.label,
                "context_sha256": sha256_text(review.context_text),
                "claim_sha256": sha256_text(claim),
                "decision": decision.to_dict(),
            }
            if signal is not None:
                row["component_signal"] = signal.to_dict()
            rows.append(row)
    payload = {
        "schema": EXPLORATION_SCHEMA,
        "qualification": "exploratory_only",
        "eligible_for_admission": False,
        "disclosure": (
            "Agent-screened development material; not human-adjudicated gold. "
            "This run cannot qualify a detector for canonical admission."
        ),
        "screen_sha256": screen.sha256,
        "review_manifest_sha256": manifest.sha256,
        "detector": {
            **detector.identity.canonical_payload(),
            "sha256": detector.identity.sha256,
        },
        "group_count": len(included),
        "case_count": len(rows),
        "score": score_support(gold, predictions),  # type: ignore[arg-type]
        "rows": sorted(rows, key=lambda row: row["case_id"]),
    }
    return {**payload, "sha256": _sha256_json(payload)}


def compare_agent_explorations(
    runs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare identical exploratory runs without producing admission semantics."""
    if len(runs) < 2:
        raise ValueError("agent exploration comparison requires at least two runs")
    baseline_rows = None
    screen_sha256 = None
    results = {}
    for key, run in sorted(runs.items()):
        if run.get("schema") != EXPLORATION_SCHEMA:
            raise ValueError(f"unsupported agent exploration schema: {key}")
        if run.get("eligible_for_admission") is not False:
            raise ValueError("comparison accepts only non-admissible exploration runs")
        supplied = str(run.get("sha256", ""))
        if supplied != _sha256_json({k: v for k, v in run.items() if k != "sha256"}):
            raise ValueError(f"agent exploration self-hash mismatch: {key}")
        identity = [
            (row["case_id"], row["expected_status"], row["kind"])
            for row in run["rows"]
        ]
        if baseline_rows is None:
            baseline_rows = identity
            screen_sha256 = run["screen_sha256"]
        elif identity != baseline_rows or run["screen_sha256"] != screen_sha256:
            raise ValueError("agent exploration runs use different cases or screen")
        supported = [row for row in run["rows"] if row["expected_status"] == "supported"]
        unsupported = [row for row in run["rows"] if row["expected_status"] != "supported"]
        binary_correct = sum(
            (row["expected_status"] == "supported")
            == (row["actual_status"] == "supported")
            for row in run["rows"]
        )
        unsupported_detected = sum(
            row["actual_status"] != "supported" for row in unsupported
        )
        results[key] = {
            "run_sha256": supplied,
            "detector": run["detector"],
            "three_way_accuracy": run["score"]["accuracy"],
            "three_way_macro_f1": run["score"]["macro_f1"],
            "binary_accuracy": binary_correct / len(run["rows"]),
            "supported_recall": sum(
                row["actual_status"] == "supported" for row in supported
            ) / len(supported),
            "unsupported_recall": unsupported_detected / len(unsupported),
            "by_kind": run["score"]["by_kind"],
        }
    payload = {
        "schema": COMPARISON_SCHEMA,
        "qualification": "exploratory_only",
        "eligible_for_admission": False,
        "screen_sha256": screen_sha256,
        "case_count": len(baseline_rows or ()),
        "results": results,
    }
    return {**payload, "sha256": _sha256_json(payload)}


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

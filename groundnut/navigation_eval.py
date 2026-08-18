"""Paired, answer-free evaluation of structured navigation."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Mapping, Protocol, Sequence

from .navigation import NavigationIndex, NavigationSelection, fetch_selected_nodes
from .navigation_cases import NavigationCase


NAVIGATION_EVALUATION_SCHEMA = "groundnut-navigation-evaluation/v1"


class Navigator(Protocol):
    identity: Any

    def select(self, index: NavigationIndex, question: str) -> NavigationSelection: ...


def run_navigation_evaluation(
    cases: Sequence[NavigationCase],
    corpus_root: str | Path,
    navigators: Sequence[Navigator],
    *,
    progress: Callable[[int, int, str, str, str], None] | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    """Score node retrieval only; no answer is generated or judged."""

    if not cases or not navigators or workers < 1:
        raise ValueError("navigation evaluation requires cases and navigators")
    corpus_root = Path(corpus_root).resolve()
    ordered_cases = sorted(cases, key=lambda row: row.case_id)
    source_texts = {}
    for case in ordered_cases:
        source_path = (corpus_root / case.index.source_id).resolve()
        if corpus_root not in source_path.parents:
            raise ValueError("navigation evaluation source escapes corpus root")
        source_texts[case.case_id] = source_path.read_text()

    tasks = [(case, navigator) for case in ordered_cases for navigator in navigators]
    seen_pairs: set[tuple[str, str]] = set()
    for case, navigator in tasks:
        pair = (case.case_id, navigator.identity.sha256)
        if pair in seen_pairs:
            raise ValueError("navigation evaluation repeats a case/navigator pair")
        seen_pairs.add(pair)

    def evaluate(task: tuple[NavigationCase, Navigator]) -> dict[str, Any]:
        case, navigator = task
        source_text = source_texts[case.case_id]
        selection = navigator.select(case.index, case.question)
        selected = set(selection.selected_node_ids)
        gold = set(case.gold_node_ids)
        context_characters = 0
        context_ratio = 0.0
        receipt = None
        if selection.status == "selected":
            _, fetched = fetch_selected_nodes(case.index, selection, source_text)
            receipt = fetched.to_dict()
            context_characters = fetched.context_characters
            context_ratio = context_characters / len(source_text)
        return {
            "case_id": case.case_id,
            "severity": case.severity,
            "navigator": navigator.identity.to_dict(),
            "selection": selection.to_dict(),
            "gold_node_count": len(gold),
            "selected_node_count": len(selected),
            "required_node_recall": len(selected & gold) / len(gold),
            "exact_gold_coverage": gold <= selected,
            "irrelevant_node_count": len(selected - gold),
            "context_characters": context_characters,
            "source_characters": len(source_text),
            "context_ratio": context_ratio,
            "receipt": receipt,
        }

    if workers == 1:
        evaluated = map(evaluate, tasks)
    else:
        executor = ThreadPoolExecutor(max_workers=workers)
        evaluated = executor.map(evaluate, tasks)
    rows = []
    try:
        for completed, row in enumerate(evaluated, 1):
            rows.append(row)
            if progress is not None:
                progress(
                    completed,
                    len(tasks),
                    row["case_id"],
                    row["navigator"]["adapter"],
                    row["selection"]["status"],
                )
    finally:
        if workers != 1:
            executor.shutdown()

    summaries = []
    identities = sorted(
        {navigator.identity.sha256: navigator.identity for navigator in navigators}.values(),
        key=lambda identity: identity.adapter,
    )
    for identity in identities:
        population = [row for row in rows if row["navigator"]["sha256"] == identity.sha256]
        selected_population = [
            row for row in population if row["selection"]["status"] == "selected"
        ]
        exact = sum(row["exact_gold_coverage"] for row in population)
        high = [row for row in population if row["severity"] == "high"]
        summaries.append(
            {
                "navigator": identity.to_dict(),
                "cases": len(population),
                "exact_gold_coverage": exact,
                "exact_gold_coverage_rate": exact / len(population),
                "mean_required_node_recall": mean(
                    row["required_node_recall"] for row in population
                ),
                "mean_selected_nodes": mean(
                    row["selected_node_count"] for row in population
                ),
                "mean_irrelevant_nodes": mean(
                    row["irrelevant_node_count"] for row in population
                ),
                "mean_context_ratio": mean(row["context_ratio"] for row in population),
                "selected_cases": len(selected_population),
                "mean_selected_nodes_when_selected": (
                    mean(row["selected_node_count"] for row in selected_population)
                    if selected_population
                    else None
                ),
                "mean_irrelevant_nodes_when_selected": (
                    mean(row["irrelevant_node_count"] for row in selected_population)
                    if selected_population
                    else None
                ),
                "mean_context_ratio_when_selected": (
                    mean(row["context_ratio"] for row in selected_population)
                    if selected_population
                    else None
                ),
                "abstentions": sum(
                    row["selection"]["status"] == "abstained" for row in population
                ),
                "failures": sum(
                    row["selection"]["status"] == "failed" for row in population
                ),
                "selection_status_counts": dict(
                    sorted(
                        Counter(
                            row["selection"]["status"] for row in population
                        ).items()
                    )
                ),
                "selection_reason_counts": dict(
                    sorted(
                        Counter(
                            row["selection"]["reason"] for row in population
                        ).items()
                    )
                ),
                "high_severity_misses": sum(not row["exact_gold_coverage"] for row in high),
            }
        )
    payload = {
        "schema": NAVIGATION_EVALUATION_SCHEMA,
        "qualification": "development_selection_only",
        "eligible_for_admission": False,
        "case_count": len(cases),
        "navigator_count": len(navigators),
        "disclosure": (
            "This evaluation measures node selection only. It does not measure "
            "answer correctness, claim support, contradiction, or truth."
        ),
        "summaries": summaries,
        "rows": rows,
    }
    return {**payload, "sha256": _sha256(payload)}


def validate_navigation_evaluation(value: Mapping[str, Any]) -> None:
    if value.get("schema") != NAVIGATION_EVALUATION_SCHEMA:
        raise ValueError("unsupported navigation evaluation schema")
    payload = {key: row for key, row in value.items() if key != "sha256"}
    if value.get("sha256") != _sha256(payload):
        raise ValueError("navigation evaluation self-hash mismatch")


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

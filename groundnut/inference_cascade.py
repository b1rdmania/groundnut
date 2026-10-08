"""Experimental report-level inference-cascade analysis.

This module consumes an explicit reasoning manifest produced outside the
canonical IC loop. It does not infer dependencies from prose, decide truth, or
create a publication gate. Its job is narrower: preserve declared reasoning
lineage, identify locally challengeable premises, and show which downstream
editorial choices depend on them.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .verification import CLAIM_PROVENANCE_CLASSES


CASCADE_MANIFEST_SCHEMA = "groundnut-inference-cascade-manifest/v1"
CASCADE_RECEIPT_SCHEMA = "groundnut-inference-cascade-receipt/v1"
CASCADE_EVALUATION_SCHEMA = "groundnut-inference-cascade-evaluation/v1"
PRESENTATIONS = {"fact", "declared_judgment", "question"}
ASSESSMENTS = {
    "supported",
    "contradicted",
    "insufficient",
    "not_assessed",
    "unavailable",
}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
MATERIALITY_LEVELS = {"low", "medium", "high"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReasoningNode:
    """One author- or reviewer-declared point in a report reasoning graph."""

    node_id: str
    text: str
    location: str
    provenance_class: str
    depends_on: tuple[str, ...]
    presentation: str
    assessment: str
    confidence: str
    materiality: str

    def __post_init__(self) -> None:
        scalar_values = (self.node_id, self.text, self.location)
        if any(not isinstance(value, str) or not value.strip() for value in scalar_values):
            raise ValueError("reasoning node id, text and location are required")
        if self.provenance_class not in CLAIM_PROVENANCE_CLASSES:
            raise ValueError(f"unknown claim provenance class: {self.provenance_class}")
        if self.presentation not in PRESENTATIONS:
            raise ValueError(f"unknown reasoning presentation: {self.presentation}")
        if self.assessment not in ASSESSMENTS:
            raise ValueError(f"unknown reasoning assessment: {self.assessment}")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unknown reasoning confidence: {self.confidence}")
        if self.materiality not in MATERIALITY_LEVELS:
            raise ValueError(f"unknown reasoning materiality: {self.materiality}")
        dependencies = tuple(sorted(self.depends_on))
        if any(not isinstance(value, str) or not value.strip() for value in dependencies):
            raise ValueError("reasoning dependencies must be non-empty ids")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError(f"{self.node_id}: duplicate reasoning dependency")
        if self.node_id in dependencies:
            raise ValueError(f"{self.node_id}: reasoning node cannot depend on itself")
        object.__setattr__(self, "depends_on", dependencies)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "text": self.text,
            "location": self.location,
            "provenance_class": self.provenance_class,
            "depends_on": list(self.depends_on),
            "presentation": self.presentation,
            "assessment": self.assessment,
            "confidence": self.confidence,
            "materiality": self.materiality,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReasoningNode":
        expected = {
            "node_id",
            "text",
            "location",
            "provenance_class",
            "depends_on",
            "presentation",
            "assessment",
            "confidence",
            "materiality",
        }
        if set(value) != expected:
            raise ValueError("reasoning node fields do not match schema")
        dependencies = value["depends_on"]
        scalar_fields = expected - {"depends_on"}
        if any(not isinstance(value[field], str) for field in scalar_fields):
            raise ValueError("reasoning node scalar fields must be strings")
        if not isinstance(dependencies, list) or any(
            not isinstance(item, str) for item in dependencies
        ):
            raise ValueError("reasoning node depends_on must be a string array")
        return cls(
            node_id=str(value["node_id"]),
            text=str(value["text"]),
            location=str(value["location"]),
            provenance_class=str(value["provenance_class"]),
            depends_on=tuple(dependencies),
            presentation=str(value["presentation"]),
            assessment=str(value["assessment"]),
            confidence=str(value["confidence"]),
            materiality=str(value["materiality"]),
        )


@dataclass(frozen=True)
class InferenceCascadeManifest:
    """Hash-bound experimental input; never constructed by ``ic_loop``."""

    report_sha256: str
    generator_key: str
    generator_version: str
    generator_sha256: str
    nodes: tuple[ReasoningNode, ...]

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.report_sha256):
            raise ValueError("cascade manifest report_sha256 must be lowercase SHA-256")
        if not self.generator_key.strip() or not self.generator_version.strip():
            raise ValueError("cascade manifest generator identity is required")
        if not _SHA256.fullmatch(self.generator_sha256):
            raise ValueError("cascade manifest generator_sha256 must be lowercase SHA-256")
        ordered = tuple(sorted(self.nodes, key=lambda node: node.node_id))
        if not ordered:
            raise ValueError("cascade manifest requires at least one reasoning node")
        identifiers = {node.node_id for node in ordered}
        if len(identifiers) != len(ordered):
            raise ValueError("cascade manifest node ids must be unique")
        for node in ordered:
            missing = set(node.depends_on) - identifiers
            if missing:
                raise ValueError(
                    f"{node.node_id}: unknown reasoning dependencies: {sorted(missing)}"
                )
        _validate_acyclic(ordered)
        object.__setattr__(self, "nodes", ordered)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": CASCADE_MANIFEST_SCHEMA,
            "report_sha256": self.report_sha256,
            "generator": {
                "key": self.generator_key,
                "version": self.generator_version,
                "sha256": self.generator_sha256,
            },
            "nodes": [node.to_dict() for node in self.nodes],
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InferenceCascadeManifest":
        if set(value) != {
            "schema",
            "report_sha256",
            "generator",
            "nodes",
            "sha256",
        }:
            raise ValueError("cascade manifest fields do not match schema")
        if value.get("schema") != CASCADE_MANIFEST_SCHEMA:
            raise ValueError("unsupported inference-cascade manifest schema")
        generator = value.get("generator")
        nodes = value.get("nodes")
        if not isinstance(generator, Mapping) or set(generator) != {
            "key",
            "version",
            "sha256",
        }:
            raise ValueError("cascade manifest generator is invalid")
        if any(
            not isinstance(generator[field], str)
            for field in ("key", "version", "sha256")
        ):
            raise ValueError("cascade manifest generator fields must be strings")
        if not isinstance(value.get("report_sha256"), str):
            raise ValueError("cascade manifest report_sha256 must be a string")
        if not isinstance(nodes, list) or any(not isinstance(row, Mapping) for row in nodes):
            raise ValueError("cascade manifest nodes must be objects")
        manifest = cls(
            report_sha256=str(value.get("report_sha256", "")),
            generator_key=str(generator["key"]),
            generator_version=str(generator["version"]),
            generator_sha256=str(generator["sha256"]),
            nodes=tuple(ReasoningNode.from_mapping(row) for row in nodes),
        )
        if value.get("sha256") != manifest.sha256:
            raise ValueError("cascade manifest self-hash mismatch")
        return manifest


@dataclass(frozen=True)
class CascadeCase:
    """One labelled development case for the experimental cascade objective."""

    case_id: str
    manifest: InferenceCascadeManifest
    expected_root_ids: tuple[str, ...]
    expected_impacted_ids: tuple[str, ...]
    protected_judgment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("cascade case id is required")
        identifiers = {node.node_id for node in self.manifest.nodes}
        for label, values in (
            ("root", self.expected_root_ids),
            ("impacted", self.expected_impacted_ids),
            ("protected", self.protected_judgment_ids),
        ):
            if len(values) != len(set(values)) or not set(values) <= identifiers:
                raise ValueError(f"cascade case {label} ids are invalid")


def analyze_inference_cascades(
    manifest: InferenceCascadeManifest,
) -> dict[str, Any]:
    """Create an advisory challenge map from declared reasoning lineage."""

    by_id = {node.node_id: node for node in manifest.nodes}
    children = _children(manifest.nodes)
    local = {
        node.node_id: challenge
        for node in manifest.nodes
        if (challenge := _local_challenge(node)) is not None
    }
    root_ids = tuple(
        node_id
        for node_id in sorted(local)
        if not (_ancestors(node_id, by_id) & set(local))
    )
    roots = []
    all_impacted: set[str] = set()
    for node_id in root_ids:
        node = by_id[node_id]
        descendants = _descendants(node_id, children)
        all_impacted.update(descendants)
        decisions = sorted(
            descendant
            for descendant in descendants
            if by_id[descendant].provenance_class == "recommendation"
        )
        roots.append(
            {
                "node_id": node_id,
                "text": node.text,
                "location": node.location,
                "challenge": local[node_id]["challenge"],
                "reason": local[node_id]["reason"],
                "priority": _priority(node, local[node_id]["challenge"]),
                "materiality": node.materiality,
                "confidence": node.confidence,
                "downstream_node_ids": sorted(descendants),
                "downstream_decision_ids": decisions,
                "blast_radius": len(descendants),
            }
        )
    local_rows = [
        {
            "node_id": node_id,
            "text": by_id[node_id].text,
            "location": by_id[node_id].location,
            **local[node_id],
        }
        for node_id in sorted(local)
    ]
    policy = {
        "schema": "groundnut-inference-cascade-policy/v1",
        "key": "advisory-cascade-experiment",
        "version": "1",
        "rules": [
            "contradicted premises are challenged regardless of presentation",
            "facts with insufficient, unavailable or unassessed support are challenged",
            "high-confidence analytical claims with weak support receive calibration challenges",
            "declared judgments are not interrupted merely because evidence does not entail them",
            "downstream nodes are exposed as impact, not relabelled as locally wrong",
            "the receipt is advisory and cannot block publication or enter the IC loop",
        ],
    }
    policy["sha256"] = _sha256_json(policy)
    payload = {
        "schema": CASCADE_RECEIPT_SCHEMA,
        "qualification": "experimental_only",
        "eligible_for_ic_loop": False,
        "publication_gate": False,
        "manifest_sha256": manifest.sha256,
        "report_sha256": manifest.report_sha256,
        "policy": policy,
        "node_count": len(manifest.nodes),
        "local_challenge_count": len(local_rows),
        "root_challenge_count": len(roots),
        "impacted_node_count": len(all_impacted),
        "impacted_decision_count": sum(
            by_id[node_id].provenance_class == "recommendation"
            for node_id in all_impacted
        ),
        "root_challenges": roots,
        "local_challenges": local_rows,
        "impacted_node_ids": sorted(all_impacted),
        "disclosure": (
            "Experimental editorial challenge map. Dependencies and assessments "
            "come from the supplied manifest; Groundnut has not inferred them from "
            "the report. Impact does not establish that a downstream claim is false."
        ),
    }
    return {**payload, "sha256": _sha256_json(payload)}


def validate_inference_cascade_receipt(value: Mapping[str, Any]) -> None:
    if value.get("schema") != CASCADE_RECEIPT_SCHEMA:
        raise ValueError("unsupported inference-cascade receipt schema")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if value.get("sha256") != _sha256_json(payload):
        raise ValueError("inference-cascade receipt self-hash mismatch")
    if value.get("eligible_for_ic_loop") is not False or value.get("publication_gate") is not False:
        raise ValueError("inference-cascade experiment cannot become a product gate")


def validate_inference_cascade_evaluation(value: Mapping[str, Any]) -> None:
    if value.get("schema") != CASCADE_EVALUATION_SCHEMA:
        raise ValueError("unsupported inference-cascade evaluation schema")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if value.get("sha256") != _sha256_json(payload):
        raise ValueError("inference-cascade evaluation self-hash mismatch")
    if value.get("eligible_for_admission") is not False:
        raise ValueError("development cascade fixtures cannot qualify the experiment")


def evaluate_inference_cascade_cases(cases: Sequence[CascadeCase]) -> dict[str, Any]:
    """Measure root/cascade recovery and interruption of protected judgments."""

    if not cases:
        raise ValueError("cascade evaluation requires at least one case")
    root_tp = root_fp = root_fn = 0
    impact_tp = impact_fp = impact_fn = 0
    protected_total = interrupted = 0
    rows = []
    seen = set()
    for case in sorted(cases, key=lambda row: row.case_id):
        if case.case_id in seen:
            raise ValueError("cascade evaluation case ids must be unique")
        seen.add(case.case_id)
        receipt = analyze_inference_cascades(case.manifest)
        predicted_roots = {row["node_id"] for row in receipt["root_challenges"]}
        predicted_impacted = set(receipt["impacted_node_ids"])
        local = {row["node_id"] for row in receipt["local_challenges"]}
        expected_roots = set(case.expected_root_ids)
        expected_impacted = set(case.expected_impacted_ids)
        protected = set(case.protected_judgment_ids)
        root_tp += len(predicted_roots & expected_roots)
        root_fp += len(predicted_roots - expected_roots)
        root_fn += len(expected_roots - predicted_roots)
        impact_tp += len(predicted_impacted & expected_impacted)
        impact_fp += len(predicted_impacted - expected_impacted)
        impact_fn += len(expected_impacted - predicted_impacted)
        protected_total += len(protected)
        interrupted += len(local & protected)
        rows.append(
            {
                "case_id": case.case_id,
                "manifest_sha256": case.manifest.sha256,
                "receipt_sha256": receipt["sha256"],
                "predicted_root_ids": sorted(predicted_roots),
                "expected_root_ids": sorted(expected_roots),
                "predicted_impacted_ids": sorted(predicted_impacted),
                "expected_impacted_ids": sorted(expected_impacted),
                "interrupted_protected_ids": sorted(local & protected),
            }
        )
    payload = {
        "schema": CASCADE_EVALUATION_SCHEMA,
        "qualification": "development_only",
        "eligible_for_admission": False,
        "case_count": len(cases),
        "metrics": {
            "root_precision": _ratio(root_tp, root_tp + root_fp),
            "root_recall": _ratio(root_tp, root_tp + root_fn),
            "impact_precision": _ratio(impact_tp, impact_tp + impact_fp),
            "impact_recall": _ratio(impact_tp, impact_tp + impact_fn),
            "protected_judgment_interruption_rate": _ratio(
                interrupted, protected_total
            ),
        },
        "counts": {
            "root_true_positive": root_tp,
            "root_false_positive": root_fp,
            "root_false_negative": root_fn,
            "impact_true_positive": impact_tp,
            "impact_false_positive": impact_fp,
            "impact_false_negative": impact_fn,
            "protected_judgments": protected_total,
            "protected_judgments_interrupted": interrupted,
        },
        "rows": rows,
        "disclosure": (
            "Development fixtures only. These metrics do not qualify dependency "
            "extraction, semantic support, or an IC publication gate."
        ),
    }
    return {**payload, "sha256": _sha256_json(payload)}


def _local_challenge(node: ReasoningNode) -> dict[str, str] | None:
    if node.assessment == "contradicted":
        return {
            "challenge": "integrity_conflict",
            "reason": "declared_assessment_contradicts_the_claim",
        }
    weak = node.assessment in {"insufficient", "not_assessed", "unavailable"}
    if weak and node.presentation == "fact":
        return {
            "challenge": "unsupported_fact",
            "reason": f"fact_presentation_with_{node.assessment}_support",
        }
    if (
        weak
        and node.confidence == "high"
        and node.provenance_class
        in {"analyst_calculation", "analyst_inference", "recommendation"}
    ):
        return {
            "challenge": "calibration_challenge",
            "reason": f"high_confidence_{node.assessment}_analytical_claim",
        }
    return None


def _priority(node: ReasoningNode, challenge: str) -> str:
    if challenge == "integrity_conflict" or node.materiality == "high":
        return "high"
    if node.materiality == "medium":
        return "medium"
    return "low"


def _children(nodes: Sequence[ReasoningNode]) -> dict[str, set[str]]:
    children = {node.node_id: set() for node in nodes}
    for node in nodes:
        for parent in node.depends_on:
            children[parent].add(node.node_id)
    return children


def _ancestors(node_id: str, by_id: Mapping[str, ReasoningNode]) -> set[str]:
    found: set[str] = set()
    pending = list(by_id[node_id].depends_on)
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(by_id[current].depends_on)
    return found


def _descendants(node_id: str, children: Mapping[str, set[str]]) -> set[str]:
    found: set[str] = set()
    pending = deque(sorted(children[node_id]))
    while pending:
        current = pending.popleft()
        if current in found:
            continue
        found.add(current)
        pending.extend(sorted(children[current]))
    return found


def _validate_acyclic(nodes: Sequence[ReasoningNode]) -> None:
    dependencies = {node.node_id: set(node.depends_on) for node in nodes}
    remaining = set(dependencies)
    ready = deque(sorted(node_id for node_id, rows in dependencies.items() if not rows))
    while ready:
        current = ready.popleft()
        remaining.remove(current)
        for node_id in sorted(remaining):
            dependencies[node_id].discard(current)
            if not dependencies[node_id] and node_id not in ready:
                ready.append(node_id)
    if remaining:
        raise ValueError(f"reasoning graph contains a cycle: {sorted(remaining)}")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()

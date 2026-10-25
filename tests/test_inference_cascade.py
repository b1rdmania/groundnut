import ast
import json
from pathlib import Path

import pytest

from groundnut import ic_loop
from groundnut.inference_cascade import (
    CascadeCase,
    InferenceCascadeManifest,
    ReasoningNode,
    analyze_inference_cascades,
    evaluate_inference_cascade_cases,
    validate_inference_cascade_evaluation,
    validate_inference_cascade_receipt,
)
from groundnut.inference_cascade_cli import main as cascade_main
from groundnut.provenance import sha256_text


def node(
    node_id,
    *,
    depends_on=(),
    provenance_class="analyst_inference",
    presentation="declared_judgment",
    assessment="supported",
    confidence="medium",
    materiality="medium",
):
    return ReasoningNode(
        node_id=node_id,
        text=f"Synthetic reasoning node {node_id}.",
        location=f"L{len(node_id)}",
        provenance_class=provenance_class,
        depends_on=tuple(depends_on),
        presentation=presentation,
        assessment=assessment,
        confidence=confidence,
        materiality=materiality,
    )


def manifest(*nodes):
    return InferenceCascadeManifest(
        report_sha256=sha256_text("public synthetic report"),
        generator_key="synthetic-reviewer",
        generator_version="1",
        generator_sha256=sha256_text("synthetic reviewer protocol v1"),
        nodes=tuple(nodes),
    )


def test_challenge_map_finds_roots_and_downstream_blast_radius():
    current = manifest(
        node(
            "evidence-error",
            provenance_class="external_evidence",
            presentation="fact",
            assessment="contradicted",
            confidence="high",
            materiality="high",
        ),
        node(
            "interpretation",
            depends_on=("evidence-error",),
            presentation="fact",
            assessment="insufficient",
            confidence="high",
            materiality="high",
        ),
        node(
            "decision",
            depends_on=("interpretation",),
            provenance_class="recommendation",
            assessment="supported",
            confidence="high",
            materiality="high",
        ),
        node(
            "legitimate-judgment",
            presentation="declared_judgment",
            assessment="insufficient",
            confidence="medium",
            materiality="high",
        ),
    )

    receipt = analyze_inference_cascades(current)

    validate_inference_cascade_receipt(receipt)
    tampered = dict(receipt)
    tampered["impacted_node_count"] = 99
    with pytest.raises(ValueError, match="self-hash"):
        validate_inference_cascade_receipt(tampered)
    assert receipt["eligible_for_ic_loop"] is False
    assert receipt["publication_gate"] is False
    assert receipt["root_challenge_count"] == 1
    [root] = receipt["root_challenges"]
    assert root["node_id"] == "evidence-error"
    assert root["text"] == "Synthetic reasoning node evidence-error."
    assert root["challenge"] == "integrity_conflict"
    assert root["downstream_node_ids"] == ["decision", "interpretation"]
    assert root["downstream_decision_ids"] == ["decision"]
    assert {row["node_id"] for row in receipt["local_challenges"]} == {
        "evidence-error",
        "interpretation",
    }
    assert "legitimate-judgment" not in {
        row["node_id"] for row in receipt["local_challenges"]
    }


def test_high_confidence_overreach_is_challenged_without_blocking_judgment():
    current = manifest(
        node(
            "overreach",
            assessment="not_assessed",
            confidence="high",
            materiality="high",
        ),
        node(
            "allowed-judgment",
            assessment="not_assessed",
            confidence="medium",
            materiality="high",
        ),
    )

    receipt = analyze_inference_cascades(current)

    assert [row["node_id"] for row in receipt["root_challenges"]] == ["overreach"]
    assert receipt["root_challenges"][0]["challenge"] == "calibration_challenge"


def test_manifest_is_hash_bound_and_rejects_cycles():
    current = manifest(node("a"), node("b", depends_on=("a",)))
    serialized = current.to_dict()

    assert InferenceCascadeManifest.from_mapping(serialized) == current
    serialized["nodes"][0]["text"] = "Rewritten after hashing."
    with pytest.raises(ValueError, match="self-hash"):
        InferenceCascadeManifest.from_mapping(serialized)
    with pytest.raises(ValueError, match="cycle"):
        manifest(node("a", depends_on=("b",)), node("b", depends_on=("a",)))


def test_seeded_evaluation_measures_cascades_and_editorial_interruption():
    cascade = manifest(
        node(
            "root",
            provenance_class="external_evidence",
            presentation="fact",
            assessment="contradicted",
            confidence="high",
            materiality="high",
        ),
        node("inference", depends_on=("root",)),
        node(
            "recommendation",
            depends_on=("inference",),
            provenance_class="recommendation",
        ),
    )
    judgment = manifest(
        node(
            "judgment",
            assessment="insufficient",
            confidence="medium",
            materiality="high",
        )
    )

    evaluation = evaluate_inference_cascade_cases(
        (
            CascadeCase(
                "cascade",
                cascade,
                expected_root_ids=("root",),
                expected_impacted_ids=("inference", "recommendation"),
            ),
            CascadeCase(
                "legitimate-judgment",
                judgment,
                expected_root_ids=(),
                expected_impacted_ids=(),
                protected_judgment_ids=("judgment",),
            ),
        )
    )

    assert evaluation["qualification"] == "development_only"
    assert evaluation["eligible_for_admission"] is False
    validate_inference_cascade_evaluation(evaluation)
    assert evaluation["metrics"] == {
        "root_precision": 1.0,
        "root_recall": 1.0,
        "impact_precision": 1.0,
        "impact_recall": 1.0,
        "protected_judgment_interruption_rate": 0.0,
    }


def test_standalone_cli_writes_advisory_receipt(tmp_path, capsys):
    current = manifest(
        node(
            "root",
            presentation="fact",
            assessment="insufficient",
            confidence="high",
            materiality="high",
        )
    )
    source = tmp_path / "manifest.json"
    report = tmp_path / "report.md"
    output = tmp_path / "receipt.json"
    report.write_text("public synthetic report")
    source.write_text(json.dumps(current.to_dict()))

    code = cascade_main(
        [
            "--report",
            str(report),
            "--manifest",
            str(source),
            "--out",
            str(output),
        ]
    )

    assert code == 0
    receipt = json.loads(output.read_text())
    assert receipt["publication_gate"] is False
    assert "advisory only" in capsys.readouterr().out

    report.write_text("changed report")
    assert (
        cascade_main(
            [
                "--report",
                str(report),
                "--manifest",
                str(source),
                "--out",
                str(output),
            ]
        )
        == 2
    )


def test_ic_loop_has_no_inference_cascade_import_or_option():
    source_path = Path(ic_loop.__file__)
    tree = ast.parse(source_path.read_text())
    imported = {
        alias.name
        for row in ast.walk(tree)
        if isinstance(row, (ast.Import, ast.ImportFrom))
        for alias in row.names
    }

    assert not any("inference_cascade" in name for name in imported)
    assert "cascade" not in source_path.read_text().casefold()

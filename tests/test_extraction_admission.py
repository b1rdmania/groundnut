import json
from pathlib import Path

import pytest

from groundnut.extraction_admission import evaluate, render_markdown


ROOT = Path(__file__).parent.parent
BENCHMARK = ROOT / "evaluation" / "artifact_extraction" / "v1" / "benchmark.json"
RECEIPT = ROOT / "results" / "artifact-extraction-admission-v1.json"


def test_frozen_cross_format_extraction_pack_is_admitted_and_reproducible():
    result = evaluate(BENCHMARK)
    frozen = json.loads(RECEIPT.read_text())

    assert result == frozen
    assert result["status"] == "admitted"
    assert result["aggregate"] == {
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "field_accuracy": 1.0,
        "location_coverage": 1.0,
        "expected": 20,
        "actual": 20,
        "categories": {
            "cited_locator": {"expected": 2, "found": 2, "missed": 0},
            "cited_quote": {"expected": 3, "found": 3, "missed": 0},
            "declared_analysis": {"expected": 3, "found": 3, "missed": 0},
            "table_label": {"expected": 4, "found": 4, "missed": 0},
            "table_numeric": {"expected": 4, "found": 4, "missed": 0},
            "typed_unsourced": {"expected": 2, "found": 2, "missed": 0},
            "uncited_numeric": {"expected": 2, "found": 2, "missed": 0},
        },
    }
    assert "not a representative estimate" in result["disclosure"]
    assert "ADMITTED" in render_markdown(result)


def test_benchmark_refuses_changed_fixture_bytes(tmp_path):
    root = BENCHMARK.parent
    copied = tmp_path / "pack"
    copied.mkdir()
    (copied / "fixtures").mkdir()
    for path in root.iterdir():
        if path.is_file():
            (copied / path.name).write_bytes(path.read_bytes())
    for path in (root / "fixtures").iterdir():
        (copied / "fixtures" / path.name).write_bytes(path.read_bytes())
    (copied / "fixtures" / "report.html").write_text("<p>Changed.</p>")

    with pytest.raises(ValueError, match="frozen hash"):
        evaluate(copied / "benchmark.json")

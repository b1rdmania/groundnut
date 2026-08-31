import json
from pathlib import Path
import shutil

import pytest

from groundnut.extraction_admission import evaluate, main, render_markdown


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


def test_below_bar_pack_is_rejected_and_cli_returns_one(tmp_path):
    copied = tmp_path / "pack"
    shutil.copytree(BENCHMARK.parent, copied)
    benchmark_path = copied / "benchmark.json"
    benchmark = json.loads(benchmark_path.read_text())
    benchmark["cases"][0]["expected"][0]["text"] = "A deliberately missed claim."
    benchmark_path.write_text(json.dumps(benchmark))

    result = evaluate(benchmark_path)
    out = tmp_path / "result.json"

    assert result["status"] == "rejected"
    assert main(["--benchmark", str(benchmark_path), "--out", str(out)]) == 1
    assert json.loads(out.read_text())["status"] == "rejected"


def test_wrong_expected_location_rejects_the_pack(tmp_path):
    copied = tmp_path / "pack"
    shutil.copytree(BENCHMARK.parent, copied)
    benchmark_path = copied / "benchmark.json"
    benchmark = json.loads(benchmark_path.read_text())
    benchmark["cases"][0]["expected"][0]["location"] = "claims[999]"
    benchmark_path.write_text(json.dumps(benchmark))

    result = evaluate(benchmark_path)

    assert result["status"] == "rejected"
    assert result["aggregate"]["field_accuracy"] < 1.0


def test_malformed_pack_cli_returns_two(tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{}")

    assert main(
        ["--benchmark", str(malformed), "--out", str(tmp_path / "out.json")]
    ) == 2

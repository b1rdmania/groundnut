"""Measure cross-format artifact extraction against a frozen labelled pack."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ArtifactProfile, extract_artifact


RESULT_SCHEMA = "groundnut-artifact-extraction-admission/v1"
FIELDS = (
    "source_uri",
    "excerpt",
    "locator",
    "question",
    "declared_analysis",
    "provenance_class",
)


def evaluate(benchmark_path: Path) -> dict[str, Any]:
    benchmark = json.loads(benchmark_path.read_text())
    if benchmark.get("schema") != "groundnut-artifact-extraction-benchmark/v1":
        raise ValueError("unsupported artifact-extraction benchmark schema")
    root = benchmark_path.parent
    profile_path = root / str(benchmark["profile"])
    if _file_sha256(profile_path) != benchmark.get("profile_file_sha256"):
        raise ValueError("benchmark profile bytes do not match the frozen hash")
    profile = ArtifactProfile.from_mapping(json.loads(profile_path.read_text()))
    thresholds = _mapping(benchmark, "thresholds")
    case_results = []
    category_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"expected": 0, "found": 0, "missed": 0}
    )
    total_expected = total_actual = total_found = 0
    total_fields = correct_fields = locations_present = 0

    for case in benchmark.get("cases", []):
        if not isinstance(case, Mapping):
            raise ValueError("benchmark cases must be objects")
        artifact_path = root / str(case["artifact"])
        artifact_sha256 = _file_sha256(artifact_path)
        if artifact_sha256 != case.get("artifact_sha256"):
            raise ValueError(f"{case['id']} artifact bytes do not match the frozen hash")
        extraction = extract_artifact(artifact_path, profile)
        if extraction.kind != case["kind"]:
            raise ValueError(
                f"{case['id']} kind mismatch: {extraction.kind} != {case['kind']}"
            )
        expected_rows = case.get("expected", [])
        if not isinstance(expected_rows, list):
            raise ValueError("case expected must be an array")
        expected = _unique_by_text(expected_rows, f"{case['id']} expected")
        actual_rows = [_claim_projection(claim) for claim in extraction.claims]
        actual = _unique_by_text(actual_rows, f"{case['id']} actual")
        found = sorted(set(expected) & set(actual))
        false_positive = sorted(set(actual) - set(expected))
        missed = sorted(set(expected) - set(actual))
        field_errors = []
        for text in found:
            for field in FIELDS:
                total_fields += 1
                if actual[text][field] == expected[text][field]:
                    correct_fields += 1
                else:
                    field_errors.append(
                        {
                            "text": text,
                            "field": field,
                            "expected": expected[text][field],
                            "actual": actual[text][field],
                        }
                    )
        locations_present += sum(bool(row["location"]) for row in actual.values())
        for text, row in expected.items():
            category = str(row["category"])
            category_totals[category]["expected"] += 1
            if text in actual:
                category_totals[category]["found"] += 1
            else:
                category_totals[category]["missed"] += 1
        metrics = _metrics(len(found), len(actual), len(expected))
        case_results.append(
            {
                "id": case["id"],
                "kind": extraction.kind,
                "artifact_sha256": artifact_sha256,
                "expected": len(expected),
                "actual": len(actual),
                **metrics,
                "field_errors": field_errors,
                "false_positive": false_positive,
                "missed": missed,
            }
        )
        total_expected += len(expected)
        total_actual += len(actual)
        total_found += len(found)

    aggregate = {
        **_metrics(total_found, total_actual, total_expected),
        "field_accuracy": correct_fields / total_fields if total_fields else 1.0,
        "location_coverage": locations_present / total_actual if total_actual else 0.0,
        "expected": total_expected,
        "actual": total_actual,
        "categories": dict(sorted(category_totals.items())),
    }
    admitted = all(
        aggregate[key] >= float(thresholds[key])
        for key in ("precision", "recall", "field_accuracy", "location_coverage")
    )
    payload = {
        "schema": RESULT_SCHEMA,
        "status": "admitted" if admitted else "rejected",
        "benchmark_sha256": _file_sha256(benchmark_path),
        "profile": {"key": profile.key, "sha256": profile.sha256},
        "profile_file_sha256": _file_sha256(profile_path),
        "thresholds": dict(thresholds),
        "disclosure": benchmark["disclosure"],
        "cases": case_results,
        "aggregate": aggregate,
    }
    payload["sha256"] = _payload_sha256(payload)
    return payload


def render_markdown(result: Mapping[str, Any]) -> str:
    aggregate = _mapping(result, "aggregate")
    lines = [
        "# Artifact extraction admission v1",
        "",
        f"Status: **{str(result['status']).upper()}**",
        "",
        str(result["disclosure"]),
        "",
        f"Receipt: `{result['sha256']}`",
        f"Benchmark: `{result['benchmark_sha256']}`",
        f"Profile: `{_mapping(result, 'profile')['key']}` / `{_mapping(result, 'profile')['sha256']}`",
        "",
        "| Kind | Expected | Actual | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in result["cases"]:
        lines.append(
            f"| `{case['kind']}` | {case['expected']} | {case['actual']} | "
            f"{case['precision']:.3f} | {case['recall']:.3f} | {case['f1']:.3f} |"
        )
    lines.extend(
        [
            "",
            f"Aggregate: precision `{aggregate['precision']:.3f}`, recall "
            f"`{aggregate['recall']:.3f}`, F1 `{aggregate['f1']:.3f}`, field "
            f"accuracy `{aggregate['field_accuracy']:.3f}`, location coverage "
            f"`{aggregate['location_coverage']:.3f}`.",
            "",
            "This admits the frozen syntax contract only. It does not establish "
            "representative accuracy on arbitrary reports.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.benchmark)
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(result))
    print(json.dumps({"status": result["status"], **result["aggregate"]}, sort_keys=True))
    return 0 if result["status"] == "admitted" else 1


def _claim_projection(claim) -> dict[str, Any]:
    return {
        "text": claim.text,
        "source_uri": claim.source.uri if claim.source else None,
        "excerpt": claim.excerpt,
        "locator": claim.locator,
        "question": claim.question,
        "declared_analysis": claim.declared_analysis,
        "provenance_class": claim.provenance_class,
        "location": claim.location,
    }


def _unique_by_text(rows, label: str) -> dict[str, Mapping[str, Any]]:
    result = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("text"), str):
            raise ValueError(f"{label} rows require text")
        text = row["text"]
        if text in result:
            raise ValueError(f"{label} texts must be unique: {text}")
        result[text] = row
    return result


def _metrics(found: int, actual: int, expected: int) -> dict[str, float]:
    precision = found / actual if actual else 0.0
    recall = found / expected if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{key} must be an object")
    return item


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

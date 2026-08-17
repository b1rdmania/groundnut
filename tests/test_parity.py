from copy import deepcopy

import pytest

from groundnut.parity import EXCLUDED_PATHS, compare_analysis


def artifact():
    return {
        "schema": "groundnut-analysis/v1",
        "domain": {
            "key": "ma_dd", "version": "1", "playbook_sha256": "playbook",
            "manifest_sha256": "manifest", "evidence_status": "experimental",
            "evidence_disclosure": "not qualified",
        },
        "source": {"source_id": "host-1", "sha256": "source", "characters": 12},
        "segments_total": 1,
        "coverage": {"complete": True, "checks": []},
        "findings": {"Change of Control": ["quote"]},
        "anchored_findings": [{
            "category_key": "change_of_control", "category_name": "Change of Control",
            "severity": 3, "quote": "quote",
            "anchor": {"source_id": "host-1", "source_sha256": "source", "quote": "quote",
                       "exact": True, "normalised": True, "offsets": [[0, 5]]},
        }],
    }


def test_parity_is_canonical_and_ignores_only_named_host_metadata():
    expected = artifact()
    actual = deepcopy(expected)
    actual["source"]["source_id"] = "different-host-id"
    actual["anchored_findings"][0]["anchor"]["source_id"] = "different-host-id"
    actual["domain"]["evidence_disclosure"] = "different deployment disclosure"

    comparison = compare_analysis(expected, actual)

    assert comparison.equal is True
    assert comparison.expected_sha256 == comparison.actual_sha256
    assert comparison.excluded_paths == EXCLUDED_PATHS


def test_parity_detects_semantic_drift():
    expected = artifact()
    actual = deepcopy(expected)
    actual["anchored_findings"][0]["anchor"]["offsets"] = [[1, 6]]

    comparison = compare_analysis(expected, actual)

    assert comparison.equal is False
    assert comparison.expected_sha256 != comparison.actual_sha256


def test_parity_rejects_unreviewed_schema_growth():
    expected = artifact()
    actual = deepcopy(expected)
    actual["new_semantic_result"] = True

    with pytest.raises(ValueError, match="unknown.*new_semantic_result"):
        compare_analysis(expected, actual)

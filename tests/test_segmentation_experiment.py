import copy

import pytest

from groundnut.segmentation_experiment import (
    Segment,
    SegmenterSpec,
    compare_segmenters,
    fixed_character_segments,
    validate_comparison,
)


def _spec(key: str) -> SegmenterSpec:
    return SegmenterSpec(key, "1", "abc123", "MIT", 20, 5)


def test_fixed_segments_reproduce_overlap_with_offsets():
    text = "0123456789" * 5
    rows = fixed_character_segments(text, max_characters=20, overlap_characters=5)
    assert [(row.start, row.end) for row in rows] == [(0, 20), (15, 35), (30, 50)]
    assert all(row.text == text[row.start : row.end] for row in rows)


def test_comparison_records_boundary_cuts_and_duplicate_exposure():
    text = "aaaaa TARGET bbbbb ccccc ddddd"

    def candidate(value: str):
        return (
            Segment(0, 9, value[:9]),
            Segment(9, 24, value[9:24]),
            Segment(24, len(value), value[24:]),
        )

    result = compare_segmenters(
        {"doc": text},
        {"doc": ("TARGET", "bb")},
        baseline_spec=_spec("baseline"),
        candidate_spec=_spec("candidate"),
        candidate_segmenter=candidate,
    )
    validate_comparison(result)
    row = result["rows"][0]
    assert row["baseline"]["duplicate_quote_exposures"] == 1
    assert row["candidate"]["boundary_cut_quote_count"] == 1
    assert result["eligible_for_admission"] is False


def test_comparison_rejects_bad_offsets_and_tampering():
    with pytest.raises(ValueError, match="offsets"):
        compare_segmenters(
            {"doc": "source text"},
            {},
            baseline_spec=_spec("baseline"),
            candidate_spec=_spec("candidate"),
            candidate_segmenter=lambda text: (Segment(0, 6, "wrong!"),),
        )

    result = compare_segmenters(
        {"doc": "source text"},
        {},
        baseline_spec=_spec("baseline"),
        candidate_spec=_spec("candidate"),
        candidate_segmenter=lambda text: (Segment(0, len(text), text),),
    )
    changed = copy.deepcopy(result)
    changed["document_count"] = 2
    with pytest.raises(ValueError, match="self-hash"):
        validate_comparison(changed)

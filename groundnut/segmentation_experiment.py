"""Controlled, non-admissible comparisons of evidence segmentation methods."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence

from .receipt import sha256_json as _sha256_json


SEGMENTATION_COMPARISON_SCHEMA = "groundnut-segmentation-comparison/v1"


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    text: str

    def validate(self, source_text: str, max_characters: int) -> None:
        if self.start < 0 or self.end <= self.start or self.end > len(source_text):
            raise ValueError("segment offsets are outside the source")
        if self.text != source_text[self.start : self.end]:
            raise ValueError("segment text does not match its source offsets")
        if len(self.text) > max_characters:
            raise ValueError("segment exceeds the shared character limit")


@dataclass(frozen=True)
class SegmenterSpec:
    key: str
    version: str
    revision: str
    licence_spdx: str
    max_characters: int
    overlap_characters: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "revision": self.revision,
            "licence_spdx": self.licence_spdx,
            "configuration": {
                "max_characters": self.max_characters,
                "overlap_characters": self.overlap_characters,
                "counter": "unicode_code_points",
            },
        }


def fixed_character_segments(
    text: str, *, max_characters: int = 20_000, overlap_characters: int = 500
) -> tuple[Segment, ...]:
    """Reproduce ``pipeline.chunking.chunk_text`` with explicit offsets."""
    if max_characters <= 0 or not 0 <= overlap_characters < max_characters:
        raise ValueError("invalid fixed-character segmentation limits")
    if not text:
        return ()
    rows = []
    start = 0
    while start < len(text):
        end = min(start + max_characters, len(text))
        rows.append(Segment(start, end, text[start:end]))
        if end == len(text):
            break
        start = end - overlap_characters
    return tuple(rows)


def compare_segmenters(
    documents: Mapping[str, str],
    predicted_spans: Mapping[str, Sequence[str]],
    *,
    baseline_spec: SegmenterSpec,
    candidate_spec: SegmenterSpec,
    candidate_segmenter: Callable[[str], Iterable[Segment]],
    largest_document_count: int = 10,
) -> dict[str, Any]:
    """Compare two segmenters over identical documents and frozen quote spans.

    This measures segmentation structure only. It does not measure extraction
    quality and cannot admit or replace a production segmenter.
    """
    if baseline_spec.max_characters != candidate_spec.max_characters:
        raise ValueError("segmenters must use the same character limit")
    if baseline_spec.overlap_characters != candidate_spec.overlap_characters:
        raise ValueError("segmenters must use the same overlap")
    if not documents:
        raise ValueError("at least one document is required")

    rows = []
    total_seconds = {"baseline": 0.0, "candidate": 0.0}
    for document_id, text in sorted(documents.items()):
        started = perf_counter()
        baseline = fixed_character_segments(
            text,
            max_characters=baseline_spec.max_characters,
            overlap_characters=baseline_spec.overlap_characters,
        )
        total_seconds["baseline"] += perf_counter() - started

        started = perf_counter()
        candidate = tuple(candidate_segmenter(text))
        total_seconds["candidate"] += perf_counter() - started

        for segment in baseline:
            segment.validate(text, baseline_spec.max_characters)
        for segment in candidate:
            segment.validate(text, candidate_spec.max_characters)
        if text and (not baseline or not candidate):
            raise ValueError("a non-empty source must produce segments")

        quotes = tuple(predicted_spans.get(document_id, ()))
        rows.append(
            {
                "document_id": document_id,
                "source_sha256": _sha256_text(text),
                "characters": len(text),
                "frozen_quote_count": len(quotes),
                "baseline": _measure(text, baseline, quotes),
                "candidate": _measure(text, candidate, quotes),
            }
        )

    corpus = [
        {
            "document_id": row["document_id"],
            "source_sha256": row["source_sha256"],
        }
        for row in rows
    ]
    frozen_quotes = [
        {
            "document_id": document_id,
            "quote_sha256": _sha256_text(quote),
            "characters": len(quote),
        }
        for document_id, quotes in sorted(predicted_spans.items())
        for quote in quotes
    ]
    payload = {
        "schema": SEGMENTATION_COMPARISON_SCHEMA,
        "qualification": "exploratory_structure_only",
        "eligible_for_admission": False,
        "disclosure": (
            "This receipt compares segmentation structure over safe development "
            "documents and frozen predicted quotes. It does not rerun extraction, "
            "measure semantic quality, or authorise a segmenter change."
        ),
        "corpus_sha256": _sha256_json(corpus),
        "frozen_quotes_sha256": _sha256_json(frozen_quotes),
        "document_count": len(rows),
        "documents_with_frozen_quotes": sum(row["frozen_quote_count"] > 0 for row in rows),
        "frozen_quote_count": sum(row["frozen_quote_count"] for row in rows),
        "segmenters": {
            "baseline": baseline_spec.to_dict(),
            "candidate": candidate_spec.to_dict(),
        },
        "summary": {
            "baseline": _summarise(rows, "baseline", total_seconds["baseline"]),
            "candidate": _summarise(rows, "candidate", total_seconds["candidate"]),
        },
        "largest_documents": sorted(
            rows, key=lambda row: (-row["characters"], row["document_id"])
        )[:largest_document_count],
        "rows": rows,
    }
    return {**payload, "sha256": _sha256_json(payload)}


def validate_comparison(value: Mapping[str, Any]) -> None:
    if value.get("schema") != SEGMENTATION_COMPARISON_SCHEMA:
        raise ValueError("unsupported segmentation comparison schema")
    supplied = str(value.get("sha256", ""))
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if supplied != _sha256_json(payload):
        raise ValueError("segmentation comparison self-hash mismatch")
    if value.get("eligible_for_admission") is not False:
        raise ValueError("structural comparison cannot be eligible for admission")


def _measure(text: str, segments: Sequence[Segment], quotes: Sequence[str]) -> dict[str, Any]:
    intervals = sorted((segment.start, segment.end) for segment in segments)
    merged_intervals = _merge_intervals(intervals)
    covered = sum(end - start for start, end in merged_intervals)
    non_whitespace_total = sum(not char.isspace() for char in text)
    non_whitespace_covered = sum(
        sum(not char.isspace() for char in text[start:end])
        for start, end in merged_intervals
    )
    grounded = 0
    contained = 0
    cut = 0
    cut_quotes = []
    duplicate_exposures = 0
    for quote in quotes:
        occurrences = _occurrences(text, quote)
        if not occurrences:
            continue
        grounded += 1
        containing_counts = [
            sum(
                segment.start <= start and end <= segment.end
                for segment in segments
            )
            for start, end in occurrences
        ]
        if any(containing_counts):
            contained += 1
            duplicate_exposures += sum(
                max(containing_count - 1, 0)
                for containing_count in containing_counts
            )
        else:
            cut += 1
            cut_quotes.append(
                {"quote_sha256": _sha256_text(quote), "characters": len(quote)}
            )
    return {
        "segment_count": len(segments),
        "multi_segment": len(segments) > 1,
        "max_segment_characters": max((len(segment.text) for segment in segments), default=0),
        "covered_character_ratio": covered / len(text) if text else 1.0,
        "covered_non_whitespace_ratio": (
            non_whitespace_covered / non_whitespace_total if non_whitespace_total else 1.0
        ),
        "overlap_character_excess": sum(len(segment.text) for segment in segments) - covered,
        "grounded_quote_count": grounded,
        "fully_contained_quote_count": contained,
        "boundary_cut_quote_count": cut,
        "boundary_cut_quotes": sorted(
            cut_quotes, key=lambda row: (row["quote_sha256"], row["characters"])
        ),
        "duplicate_quote_exposures": duplicate_exposures,
    }


def _summarise(rows: Sequence[Mapping[str, Any]], key: str, seconds: float) -> dict[str, Any]:
    measured = [row[key] for row in rows]
    return {
        "runtime_seconds": seconds,
        "segment_count": sum(row["segment_count"] for row in measured),
        "multi_segment_document_count": sum(row["multi_segment"] for row in measured),
        "minimum_non_whitespace_coverage": min(
            row["covered_non_whitespace_ratio"] for row in measured
        ),
        "grounded_quote_count": sum(row["grounded_quote_count"] for row in measured),
        "fully_contained_quote_count": sum(
            row["fully_contained_quote_count"] for row in measured
        ),
        "boundary_cut_quote_count": sum(row["boundary_cut_quote_count"] for row in measured),
        "duplicate_quote_exposures": sum(
            row["duplicate_quote_exposures"] for row in measured
        ),
    }


def _occurrences(text: str, quote: str) -> tuple[tuple[int, int], ...]:
    if not quote:
        return ()
    rows = []
    start = 0
    while True:
        found = text.find(quote, start)
        if found < 0:
            break
        rows.append((found, found + len(quote)))
        start = found + 1
    return tuple(rows)


def _merge_intervals(
    intervals: Sequence[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    merged = []
    last_start = last_end = 0
    for index, (start, end) in enumerate(intervals):
        if index == 0:
            last_start, last_end = start, end
        elif start > last_end:
            merged.append((last_start, last_end))
            last_start, last_end = start, end
        else:
            last_end = max(last_end, end)
    if intervals:
        merged.append((last_start, last_end))
    return tuple(merged)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

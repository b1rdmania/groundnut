"""Mechanical claim-to-source verification.

This layer answers whether a cited excerpt can be anchored in a source. It
never upgrades excerpt presence into claim support or truth; semantic judging
is a separate adapter and result field.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any

from .metrics import MetricEnvelope
from .provenance import sha256_text
from .sources import EvidenceWindow, SourceReference, SourceResolution


CLAIM_PROVENANCE_CLASSES = {
    "external_evidence",
    "company_assertion",
    "analyst_calculation",
    "analyst_inference",
    "recommendation",
    "open_question",
    "unclassified",
}
ANALYTICAL_PROVENANCE_SCHEMA = "groundnut-analytical-provenance/v1"
CALCULATION_LINEAGE_SCHEMA = "groundnut-calculation-lineage/v1"
ANALYST_PROVENANCE_CLASSES = {
    "analyst_calculation",
    "analyst_inference",
    "recommendation",
}
VERIFICATION_OUTCOMES = {
    "not_applicable",
    "unresolvable_source",
    "source_unavailable",
    "no_excerpt",
    "excerpt_found",
    "excerpt_ambiguous",
    "excerpt_not_found",
    "evidence_window_incomplete",
}


@dataclass(frozen=True)
class CalculationInput:
    name: str
    value: str
    source_claim_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_claim_ids", tuple(sorted(self.source_claim_ids))
        )
        if not self.name.strip() or not self.value.strip():
            raise ValueError("calculation input name and value are required")
        if any(not claim_id.strip() for claim_id in self.source_claim_ids):
            raise ValueError("calculation input source claim ids must not be empty")
        if len(self.source_claim_ids) != len(set(self.source_claim_ids)):
            raise ValueError("calculation input source claim ids must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "source_claim_ids": list(self.source_claim_ids),
        }


@dataclass(frozen=True)
class CalculationLineage:
    formula: str
    inputs: tuple[CalculationInput, ...]
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(sorted(self.inputs, key=lambda row: row.name)))
        if not self.formula.strip() or not self.inputs:
            raise ValueError("calculation formula and at least one named input are required")
        names = [row.name for row in self.inputs]
        if len(names) != len(set(names)):
            raise ValueError("calculation input names must be unique")
        if self.note is not None and not self.note.strip():
            raise ValueError("calculation lineage note must not be empty")

    @property
    def formula_sha256(self) -> str:
        return sha256_text(self.formula)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALCULATION_LINEAGE_SCHEMA,
            "formula": self.formula,
            "formula_sha256": self.formula_sha256,
            "inputs": [row.to_dict() for row in self.inputs],
            "note": self.note,
        }


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    source: SourceReference | None = None
    excerpt: str | None = None
    locator: str | None = None
    declared_analysis: bool = False
    provenance_class: str = "unclassified"
    question: str | None = None
    location: str | None = None
    calculation_lineage: CalculationLineage | None = None

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.text.strip():
            raise ValueError("claim identity and text are required")
        if self.question is not None and not self.question.strip():
            raise ValueError("claim verification question must not be empty")
        if self.locator is not None and not self.locator.strip():
            raise ValueError("claim source locator must not be empty")
        if self.provenance_class not in CLAIM_PROVENANCE_CLASSES:
            raise ValueError(f"unknown claim provenance class: {self.provenance_class}")
        if self.declared_analysis and self.provenance_class == "unclassified":
            object.__setattr__(self, "provenance_class", "analyst_inference")
        elif self.declared_analysis and self.provenance_class not in ANALYST_PROVENANCE_CLASSES:
            raise ValueError("declared analysis conflicts with provenance class")
        elif self.provenance_class in ANALYST_PROVENANCE_CLASSES:
            object.__setattr__(self, "declared_analysis", True)
        if (
            self.calculation_lineage is not None
            and self.provenance_class != "analyst_calculation"
        ):
            raise ValueError(
                "calculation lineage requires analyst_calculation provenance"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "source": (
                {"source_id": self.source.source_id, "uri": self.source.uri}
                if self.source
                else None
            ),
            "excerpt": self.excerpt,
            "locator": self.locator,
            "declared_analysis": self.declared_analysis,
            "analytical_provenance": {
                "schema": ANALYTICAL_PROVENANCE_SCHEMA,
                "class": self.provenance_class,
                "calculation_lineage_status": (
                    "declared"
                    if self.calculation_lineage is not None
                    else "missing"
                    if self.provenance_class == "analyst_calculation"
                    else "not_applicable"
                ),
                "calculation_lineage": (
                    self.calculation_lineage.to_dict()
                    if self.calculation_lineage is not None
                    else None
                ),
            },
            "question": self.question,
            "location": self.location,
        }


@dataclass(frozen=True)
class MatchOutcome:
    anchor: str
    method: str
    score: float
    normalisation_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifiedClaim:
    claim: Claim
    anchor: str | None
    outcome: str
    method: str
    score: float | None
    support: str
    note: str
    failure: str | None = None
    evidence_window: EvidenceWindow | None = None
    normalisation_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "normalisation_reasons", tuple(sorted(set(self.normalisation_reasons)))
        )
        if self.outcome not in VERIFICATION_OUTCOMES:
            raise ValueError(f"unknown verification outcome: {self.outcome}")
        if self.outcome.startswith("excerpt_") or self.outcome in {
            "no_excerpt",
            "evidence_window_incomplete",
        }:
            if self.evidence_window is None:
                raise ValueError("source verification outcome requires an evidence window")
        if self.outcome == "evidence_window_incomplete" and (
            self.anchor != "not_found"
            or self.evidence_window is None
            or self.evidence_window.truncation == "complete"
        ):
            raise ValueError("incomplete outcome requires a non-complete searched window")
        if self.outcome == "excerpt_not_found" and (
            self.anchor != "not_found"
            or self.evidence_window is None
            or self.evidence_window.truncation != "complete"
        ):
            raise ValueError("not-found outcome requires a complete searched window")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-claim-verification/v4",
            "claim": self.claim.to_dict(),
            "anchor": self.anchor,
            "outcome": self.outcome,
            "method": self.method,
            "score": self.score,
            "normalisation_reasons": list(self.normalisation_reasons),
            "support": self.support,
            "note": self.note,
            "failure": self.failure,
            "evidence_window": (
                self.evidence_window.to_dict() if self.evidence_window else None
            ),
        }


_TRANS = str.maketrans(
    {"‘": "'", "’": "'", "‛": "'", "“": '"', "”": '"', "–": "-", "—": "-"}
)


def normalise(value: str) -> str:
    value = value.casefold().translate(_TRANS)
    value = re.sub(r"[^\w$%£€.,'\"-]+", " ", value, flags=re.UNICODE)
    return " ".join(value.replace("_", " ").split())


def _normalise_with_map(value: str) -> tuple[str, list[int]]:
    """Return the baseline normalisation and a raw-character provenance map."""

    output: list[str] = []
    offsets: list[int] = []
    pending_space: int | None = None
    for index, raw_character in enumerate(value):
        for character in raw_character.casefold().translate(_TRANS):
            if character == "_" or not re.match(r"[\w$%£€.,'\"-]", character):
                if output and pending_space is None:
                    pending_space = index
                continue
            if pending_space is not None:
                output.append(" ")
                offsets.append(pending_space)
                pending_space = None
            output.append(character)
            offsets.append(index)
    return "".join(output), offsets


def _dimension_normalise(value: str, *, omit: str | None = None) -> str:
    if omit != "case":
        value = value.casefold()
    if omit != "quotes":
        value = value.translate(str.maketrans({"‘": "'", "’": "'", "‛": "'", "“": '"', "”": '"'}))
    if omit != "dashes":
        value = value.translate(str.maketrans({"–": "-", "—": "-"}))
    if omit != "punctuation":
        characters: list[str] = []
        for index, character in enumerate(value):
            if character.isspace() or re.fullmatch(
                r"[\w$%£€.,'\"-]", character, flags=re.UNICODE
            ):
                characters.append(character)
            elif (
                (not characters or not characters[-1].isspace())
                and (index + 1 == len(value) or not value[index + 1].isspace())
            ):
                characters.append(" ")
        value = "".join(characters)
    if omit != "whitespace":
        value = " ".join(value.replace("_", " ").split())
    return value


def _normalisation_reasons(excerpt: str, source_text: str, start: int) -> tuple[str, ...]:
    needle, _ = _normalise_with_map(excerpt)
    haystack, offsets = _normalise_with_map(source_text)
    if not needle or not offsets:
        return ()
    end = start + len(needle) - 1
    candidate = source_text[offsets[start] : offsets[end] + 1]
    reasons = [
        reason
        for reason in ("case", "whitespace", "quotes", "dashes", "punctuation")
        if _dimension_normalise(excerpt, omit=reason)
        != _dimension_normalise(candidate, omit=reason)
    ]
    # A defensive fallback keeps the contract honest if a future Unicode edge
    # case is normalised by the baseline but is outside the named dimensions.
    return tuple(reasons or ("punctuation",))


def anchor_excerpt(excerpt: str, source_text: str) -> MatchOutcome:
    if excerpt and excerpt in source_text:
        return MatchOutcome("found", "byte_exact", 1.0)
    needle = normalise(excerpt)
    haystack = normalise(source_text)
    if not needle or not haystack:
        return MatchOutcome("not_found", "fuzzy", 0.0)
    normalised_at = haystack.find(needle)
    if normalised_at >= 0:
        return MatchOutcome(
            "found",
            "normalised",
            1.0,
            _normalisation_reasons(excerpt, source_text, normalised_at),
        )
    score = best_window_similarity(needle, haystack)
    if score >= 0.80:
        return MatchOutcome("ambiguous", "fuzzy", score)
    return MatchOutcome("not_found", "fuzzy", score)


def _bigrams(value: str) -> Counter[str]:
    return Counter(value[index : index + 2] for index in range(len(value) - 1))


def _dice(left: str, right: str) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    a, b = _bigrams(left), _bigrams(right)
    overlap = sum(min(count, b.get(gram, 0)) for gram, count in a.items())
    return 2 * overlap / ((len(left) - 1) + (len(right) - 1))


def best_window_similarity(needle: str, haystack: str) -> float:
    window = min(len(haystack), len(needle))
    if len(haystack) <= window:
        return _dice(needle, haystack)
    coarse = max(1, len(needle) // 4)
    best = 0.0
    best_at = 0
    for index in range(0, len(haystack) - window + 1, coarse):
        score = _dice(needle, haystack[index : index + window])
        if score > best:
            best, best_at = score, index
    start = max(0, best_at - coarse)
    end = min(len(haystack) - window, best_at + coarse)
    for index in range(start, end + 1):
        best = max(best, _dice(needle, haystack[index : index + window]))
    return best


def verify_claim(claim: Claim, resolution: SourceResolution | None) -> VerifiedClaim:
    """Mechanically verify citation apparatus without judging claim support."""
    if claim.source is None:
        if claim.locator:
            return VerifiedClaim(
                claim=claim,
                anchor=None,
                outcome="unresolvable_source",
                method="locator",
                score=None,
                support="not_assessed",
                failure="unresolvable_source",
                note=(
                    "A source locator is preserved, but no resolvable source URI "
                    "is attached; no source or support check was possible."
                ),
            )
        typed = claim.provenance_class != "unclassified"
        return VerifiedClaim(
            claim=claim,
            anchor=None,
            outcome="not_applicable",
            method="provenance" if typed else "no_source",
            score=None,
            support="not_assessed",
            note=(
                f"Artifact declares {claim.provenance_class}; this class does not establish support."
                if typed
                else "No checkable source is attached."
            ),
        )
    if resolution is None or not resolution.ok:
        failure = resolution.failure if resolution else "source_unreachable"
        return VerifiedClaim(
            claim=claim,
            anchor=None,
            outcome="source_unavailable",
            method="fetch_failed",
            score=None,
            support="not_assessed",
            failure=failure,
            note=f"Source could not be checked ({failure}); this is not a truth verdict.",
        )
    if resolution.source.reference != claim.source:
        return VerifiedClaim(
            claim=claim,
            anchor=None,
            outcome="source_unavailable",
            method="fetch_failed",
            score=None,
            support="not_assessed",
            failure="source_changed",
            note="Resolved source identity does not match the claim citation.",
        )
    if not claim.excerpt:
        return VerifiedClaim(
            claim=claim,
            anchor=None,
            outcome="no_excerpt",
            method="locator" if claim.locator else "no_excerpt",
            score=None,
            support="not_assessed",
            note="Source is readable but no verbatim excerpt was supplied; semantic review is required.",
            evidence_window=resolution.source.evidence_window,
        )
    match = anchor_excerpt(claim.excerpt, resolution.source.text)
    window = resolution.source.evidence_window
    if window.truncation == "hollow":
        match = MatchOutcome("not_found", "unusable_evidence_window", 0.0)
        outcome = "evidence_window_incomplete"
    elif match.anchor == "found":
        outcome = "excerpt_found"
    elif match.anchor == "ambiguous":
        outcome = "excerpt_ambiguous"
    elif window.truncation == "complete":
        outcome = "excerpt_not_found"
    else:
        outcome = "evidence_window_incomplete"
    return VerifiedClaim(
        claim=claim,
        anchor=match.anchor,
        outcome=outcome,
        method=match.method,
        score=match.score,
        support="not_assessed",
        note=(
            "Excerpt anchored in source; claim support has not been assessed."
            if match.anchor == "found"
            else (
                "Excerpt was not found, but the searchable evidence window is incomplete; "
                "absence cannot be concluded."
                if outcome == "evidence_window_incomplete"
                else "Excerpt was not conclusively anchored; claim support has not been assessed."
            )
        ),
        evidence_window=window,
        normalisation_reasons=match.normalisation_reasons,
    )


def verification_metrics(rows: list[VerifiedClaim]) -> dict[str, Any]:
    cited = [
        row
        for row in rows
        if row.claim.source is not None or row.claim.locator is not None
    ]
    resolvable = [row for row in cited if row.claim.source is not None]
    readable = [row for row in resolvable if row.method != "fetch_failed"]
    excerpts = [row for row in resolvable if row.claim.excerpt]
    anchored = [row for row in excerpts if row.anchor == "found"]
    byte_exact_anchored = [row for row in anchored if row.method == "byte_exact"]
    normalised_anchored = [row for row in anchored if row.method == "normalised"]
    calculations = [
        row for row in rows if row.claim.provenance_class == "analyst_calculation"
    ]
    calculations_with_lineage = [
        row for row in calculations if row.claim.calculation_lineage is not None
    ]
    anchor_outcomes = {
        "byte_exact_found": len(byte_exact_anchored),
        "normalised_found": len(normalised_anchored),
        "fuzzy_ambiguous": sum(
            row.method == "fuzzy" and row.anchor == "ambiguous" for row in excerpts
        ),
        "fuzzy_not_found": sum(
            row.method == "fuzzy"
            and row.outcome == "excerpt_not_found"
            for row in excerpts
        ),
        "evidence_window_incomplete": sum(
            row.outcome == "evidence_window_incomplete" for row in excerpts
        ),
        "locator_only": sum(row.method == "locator" for row in cited),
        "unresolvable_source": sum(
            row.outcome == "unresolvable_source" for row in cited
        ),
        "no_excerpt": sum(row.method == "no_excerpt" for row in cited),
        "fetch_failed": sum(row.method == "fetch_failed" for row in cited),
        "no_source": sum(row.method == "no_source" for row in rows),
        "typed_provenance": sum(row.method == "provenance" for row in rows),
    }
    rates = (
        MetricEnvelope(
            "citation_coverage",
            "coverage",
            len(cited),
            len(rows),
            "all detected claims",
        ),
        MetricEnvelope(
            "source_resolvability",
            "resolvability",
            len(resolvable),
            len(cited),
            "claims with declared evidence",
        ),
        MetricEnvelope(
            "source_accessibility",
            "accessibility",
            len(readable),
            len(resolvable),
            "claims with a resolvable source URI",
        ),
        MetricEnvelope(
            "excerpt_anchoring",
            "anchoring",
            len(anchored),
            len(excerpts),
            "cited claims with a supplied verbatim excerpt",
        ),
        MetricEnvelope(
            "byte_exact_anchor_share",
            "anchoring_method",
            len(byte_exact_anchored),
            len(anchored),
            "anchored excerpts",
        ),
        MetricEnvelope(
            "normalised_anchor_share",
            "anchoring_method",
            len(normalised_anchored),
            len(anchored),
            "anchored excerpts",
        ),
        MetricEnvelope(
            "calculation_lineage_coverage",
            "provenance_completeness",
            len(calculations_with_lineage),
            len(calculations),
            "claims declared analyst_calculation",
        ),
    )
    per_provenance = {}
    for provenance_class in sorted({row.claim.provenance_class for row in rows}):
        population = [
            row for row in rows if row.claim.provenance_class == provenance_class
        ]
        population_cited = [
            row
            for row in population
            if row.claim.source is not None or row.claim.locator is not None
        ]
        population_resolvable = [
            row for row in population_cited if row.claim.source is not None
        ]
        per_provenance[provenance_class] = {
            "claims": len(population),
            "cited_claims": len(population_cited),
            "resolvable_citations": len(population_resolvable),
            "unresolvable_locator_claims": sum(
                row.outcome == "unresolvable_source" for row in population
            ),
            "no_source": sum(row.method == "no_source" for row in population),
            "typed_provenance": sum(
                row.method == "provenance" for row in population
            ),
            "citation_coverage": MetricEnvelope(
                "citation_coverage",
                "coverage_by_provenance",
                len(population_cited),
                len(population),
                f"claims declared {provenance_class}",
            ).to_dict(),
        }
    return {
        "schema": "groundnut-verification-metrics/v6",
        "counts": {
            "detected_claims": len(rows),
            "cited_claims": len(cited),
            "resolvable_citations": len(resolvable),
            "unresolvable_locator_claims": sum(
                row.outcome == "unresolvable_source" for row in cited
            ),
            "readable_citations": len(readable),
            "excerpt_claims": len(excerpts),
            "anchored_excerpts": len(anchored),
            "byte_exact_anchored_excerpts": len(byte_exact_anchored),
            "normalised_anchored_excerpts": len(normalised_anchored),
            "analyst_calculations": len(calculations),
            "calculations_with_lineage": len(calculations_with_lineage),
        },
        "anchor_outcome_counts": anchor_outcomes,
        "by_provenance_class": per_provenance,
        "rates": {metric.name: metric.to_dict() for metric in rates},
    }

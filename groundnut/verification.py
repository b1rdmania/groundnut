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

from .sources import SourceReference, SourceResolution


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    source: SourceReference | None = None
    excerpt: str | None = None
    locator: str | None = None
    declared_analysis: bool = False
    question: str | None = None

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
            "question": self.question,
        }


@dataclass(frozen=True)
class MatchOutcome:
    anchor: str
    method: str
    score: float


@dataclass(frozen=True)
class VerifiedClaim:
    claim: Claim
    anchor: str | None
    method: str
    score: float | None
    support: str
    note: str
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-claim-verification/v1",
            "claim": self.claim.to_dict(),
            "anchor": self.anchor,
            "method": self.method,
            "score": self.score,
            "support": self.support,
            "note": self.note,
            "failure": self.failure,
        }


_TRANS = str.maketrans(
    {"‘": "'", "’": "'", "‛": "'", "“": '"', "”": '"', "–": "-", "—": "-"}
)
_NUMERIC = re.compile(r"[$£€]?\d[\d,.]*%?")


def normalise(value: str) -> str:
    value = value.casefold().translate(_TRANS)
    value = re.sub(r"[^\w$%£€.,'\"-]+", " ", value, flags=re.UNICODE)
    return " ".join(value.replace("_", " ").split())


def numeric_tokens(normalised: str) -> tuple[str, ...]:
    return tuple(_NUMERIC.findall(normalised))


def anchor_excerpt(excerpt: str, source_text: str) -> MatchOutcome:
    needle = normalise(excerpt)
    haystack = normalise(source_text)
    if not needle or not haystack:
        return MatchOutcome("not_found", "exact", 0.0)
    if needle in haystack:
        return MatchOutcome("found", "exact", 1.0)
    score = best_window_similarity(needle, haystack)
    if score >= 0.95:
        if all(token in haystack for token in numeric_tokens(needle)):
            return MatchOutcome("found", "fuzzy", score)
        return MatchOutcome("ambiguous", "fuzzy", score)
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
    window = min(len(haystack), int(len(needle) * 1.2 + 0.999999))
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
    for index in range(start, end + 1, 7):
        best = max(best, _dice(needle, haystack[index : index + window]))
    return best


def verify_claim(claim: Claim, resolution: SourceResolution | None) -> VerifiedClaim:
    """Mechanically verify citation apparatus without judging claim support."""
    if claim.source is None:
        return VerifiedClaim(
            claim=claim,
            anchor=None,
            method="provenance" if claim.declared_analysis else "no_source",
            score=None,
            support="declared_analysis" if claim.declared_analysis else "not_assessed",
            note=(
                "Declared analysis has no external source; review its inputs and method."
                if claim.declared_analysis
                else "No checkable source is attached."
            ),
        )
    if resolution is None or not resolution.ok:
        failure = resolution.failure if resolution else "source_unreachable"
        return VerifiedClaim(
            claim=claim,
            anchor=None,
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
            method="locator" if claim.locator else "no_excerpt",
            score=None,
            support="not_assessed",
            note="Source is readable but no verbatim excerpt was supplied; semantic review is required.",
        )
    match = anchor_excerpt(claim.excerpt, resolution.source.text)
    return VerifiedClaim(
        claim=claim,
        anchor=match.anchor,
        method=match.method,
        score=match.score,
        support="not_assessed",
        note=(
            "Excerpt anchored in source; claim support has not been assessed."
            if match.anchor == "found"
            else "Excerpt was not conclusively anchored; claim support has not been assessed."
        ),
    )


def verification_metrics(rows: list[VerifiedClaim]) -> dict[str, float | int | None]:
    cited = [row for row in rows if row.claim.source is not None]
    readable = [row for row in cited if row.method != "fetch_failed"]
    excerpts = [row for row in cited if row.claim.excerpt]
    anchored = [row for row in excerpts if row.anchor == "found"]
    return {
        "detected_claims": len(rows),
        "cited_claims": len(cited),
        "citation_coverage": _ratio(len(cited), len(rows)),
        "readable_citations": len(readable),
        "source_accessibility": _ratio(len(readable), len(cited)),
        "excerpt_claims": len(excerpts),
        "anchored_excerpts": len(anchored),
        "excerpt_anchoring": _ratio(len(anchored), len(excerpts)),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None

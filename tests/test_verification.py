import json
from pathlib import Path

from groundnut.sources import (
    EvidenceWindow,
    ResolvedSource,
    SourceReference,
    SourceResolution,
)
import pytest

from groundnut.verification import (
    CalculationInput,
    CalculationLineage,
    Claim,
    anchor_excerpt,
    verification_metrics,
    verify_claim,
)


BOUNDARY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "evidence_window_boundary.json"
)


def resolved(reference, text, *, truncation="complete"):
    return SourceResolution(
        source=ResolvedSource(
            reference=reference,
            text=text,
            fetched_at="2026-08-17T00:00:00Z",
            status=200,
            media_type="text/plain",
            evidence_window=EvidenceWindow.from_text(
                text,
                original_bytes=len(text.encode()),
                original_characters=len(text),
                truncation=truncation,
                extraction_method="test-fixture/v1",
            ),
        )
    )


def test_claim_rejects_blank_verification_question():
    with pytest.raises(ValueError, match="question"):
        Claim("c1", "A claim", question="  ")


def test_claim_rejects_blank_source_locator():
    with pytest.raises(ValueError, match="locator"):
        Claim("c1", "A claim", locator="  ")


def test_exact_and_format_normalised_excerpt_anchor():
    exact = anchor_excerpt("Revenue was $14.2M.", "Revenue was $14.2M.")
    assert (exact.anchor, exact.method, exact.normalisation_reasons) == (
        "found",
        "byte_exact",
        (),
    )
    outcome = anchor_excerpt(
        "REVENUE  WAS  $14.2M — audited", "Revenue was $14.2M - audited"
    )
    assert outcome.anchor == "found"
    assert outcome.method == "normalised"
    assert set(outcome.normalisation_reasons) == {"case", "whitespace", "dashes"}


@pytest.mark.parametrize(
    ("excerpt", "source", "reason"),
    [
        ("Alpha BETA", "Alpha beta", "case"),
        ("Alpha   beta", "Alpha beta", "whitespace"),
        ("She said “yes”", 'She said "yes"', "quotes"),
        ("Pages 4–8", "Pages 4-8", "dashes"),
        ("Pages 4—8", "Pages 4-8", "dashes"),
        ("Alpha: beta", "Alpha beta", "punctuation"),
    ],
)
def test_normalised_matches_name_the_raw_byte_difference(excerpt, source, reason):
    outcome = anchor_excerpt(excerpt, source)
    assert outcome.method == "normalised"
    assert outcome.normalisation_reasons == (reason,)


def test_repeated_byte_exact_excerpt_is_found_without_uniqueness_claim():
    outcome = anchor_excerpt("same bytes", "same bytes and same bytes")
    assert (outcome.anchor, outcome.method, outcome.score) == (
        "found",
        "byte_exact",
        1.0,
    )


def test_fuzzy_numeric_guard_refuses_wrong_amount():
    outcome = anchor_excerpt(
        "The reported revenue was $14.2M for the period.",
        "The reported revenue was $4.2M for the period.",
    )
    assert outcome.anchor != "found"


def test_anchor_presence_never_becomes_support():
    reference = SourceReference("filing", "https://example.test/filing")
    claim = Claim(
        "c1",
        "The company is certain to win.",
        source=reference,
        excerpt="Revenue increased by 10%.",
    )
    result = verify_claim(claim, resolved(reference, "Revenue increased by 10%."))

    assert result.anchor == "found"
    assert result.support == "not_assessed"
    assert "support has not been assessed" in result.note


def test_bare_locator_is_unresolvable_not_unsourced_or_not_applicable():
    claim = Claim(
        "locator",
        "Confidential revenue was £4.2m.",
        locator="investment memo, page 7",
    )

    result = verify_claim(claim, None)

    assert result.outcome == "unresolvable_source"
    assert result.method == "locator"
    assert result.failure == "unresolvable_source"
    assert result.claim.locator == "investment memo, page 7"
    assert result.to_dict()["schema"] == "groundnut-claim-verification/v4"


def test_calculation_lineage_is_hash_bound_but_never_becomes_support():
    lineage = CalculationLineage(
        formula="arr = customers * annual_price",
        inputs=(
            CalculationInput("annual_price", "£12,000", ("price",)),
            CalculationInput("customers", "5", ("customers",)),
        ),
    )
    claim = Claim(
        "arr",
        "Modelled ARR is £60,000.",
        provenance_class="analyst_calculation",
        calculation_lineage=lineage,
    )
    result = verify_claim(claim, None)
    payload = result.to_dict()["claim"]["analytical_provenance"]

    assert payload["calculation_lineage_status"] == "declared"
    assert payload["calculation_lineage"]["formula_sha256"] == lineage.formula_sha256
    assert [row["name"] for row in payload["calculation_lineage"]["inputs"]] == [
        "annual_price",
        "customers",
    ]
    assert result.support == "not_assessed"

    metrics = verification_metrics([result])
    lineage_rate = metrics["rates"]["calculation_lineage_coverage"]
    assert (lineage_rate["numerator"], lineage_rate["denominator"]) == (1, 1)

    with pytest.raises(ValueError, match="requires analyst_calculation"):
        Claim(
            "wrong",
            "Do this.",
            provenance_class="recommendation",
            calculation_lineage=lineage,
        )


def test_fetch_failure_is_not_scored_as_fabrication():
    reference = SourceReference("filing", "https://example.test/paywall")
    result = verify_claim(
        Claim("c2", "A sourced claim", source=reference, excerpt="excerpt"),
        SourceResolution(source=None, failure="source_paywalled"),
    )

    assert result.anchor is None
    assert result.failure == "source_paywalled"
    assert result.support == "not_assessed"


def test_boundary_fixture_distinguishes_found_from_incomplete_window():
    fixture = json.loads(BOUNDARY_FIXTURE.read_text())
    reference = SourceReference(fixture["source_id"], fixture["uri"])
    claim = Claim(
        "c-window",
        "The permit records a later deadline.",
        source=reference,
        excerpt=fixture["after_boundary_excerpt"],
    )
    captured = fixture["captured_text"]

    complete = verify_claim(claim, resolved(reference, captured))
    incomplete = verify_claim(
        claim, resolved(reference, captured, truncation="truncated")
    )

    assert complete.anchor == "not_found"
    assert complete.outcome == "excerpt_not_found"
    assert incomplete.anchor == "not_found"
    assert incomplete.outcome == "evidence_window_incomplete"
    assert incomplete.evidence_window.truncation == "truncated"
    before = verify_claim(
        Claim(
            "c-before",
            "Permit issued.",
            source=reference,
            excerpt=fixture["before_boundary_excerpt"],
        ),
        resolved(reference, captured, truncation="truncated"),
    )

    assert before.anchor == "found"
    assert before.outcome == "excerpt_found"
    assert before.evidence_window.truncation == "truncated"


def test_metrics_keep_coverage_accessibility_and_anchoring_separate():
    reference = SourceReference("s1", "https://example.test/a")
    rows = [
        verify_claim(
            Claim("c1", "Claim", source=reference, excerpt="source text"),
            resolved(reference, "source text"),
        ),
        verify_claim(Claim("c2", "Unsourced"), None),
    ]

    metrics = verification_metrics(rows)
    assert metrics["schema"] == "groundnut-verification-metrics/v5"
    assert metrics["rates"]["citation_coverage"] == {
        "schema": "groundnut-metric-envelope/v1",
        "name": "citation_coverage",
        "class": "coverage",
        "numerator": 1,
        "denominator": 2,
        "population": "all detected claims",
        "value": 0.5,
    }
    assert metrics["rates"]["source_accessibility"]["value"] == 1.0
    assert metrics["rates"]["source_resolvability"]["value"] == 1.0
    assert metrics["rates"]["excerpt_anchoring"]["value"] == 1.0
    assert metrics["anchor_outcome_counts"]["no_source"] == 1
    by_class = metrics["by_provenance_class"]["unclassified"]
    assert by_class["citation_coverage"]["denominator"] == 2


def test_metrics_count_bare_locator_as_declared_but_unresolvable_evidence():
    rows = [
        verify_claim(
            Claim("c1", "Confidential claim.", locator="memo, page 7"), None
        ),
        verify_claim(Claim("c2", "No evidence declared."), None),
    ]

    metrics = verification_metrics(rows)

    assert metrics["counts"]["cited_claims"] == 1
    assert metrics["counts"]["resolvable_citations"] == 0
    assert metrics["counts"]["unresolvable_locator_claims"] == 1
    assert metrics["rates"]["citation_coverage"]["value"] == 0.5
    assert metrics["rates"]["source_resolvability"]["value"] == 0.0
    assert metrics["rates"]["source_accessibility"]["value"] is None
    assert metrics["anchor_outcome_counts"]["unresolvable_source"] == 1


def test_metrics_keep_fuzzy_anchors_as_their_own_population():
    reference = SourceReference("s1", "https://example.test/a")
    source = (
        "The company reported consolidated revenue of $14.2 million for the "
        "financial year ending 31 December 2025."
    )
    drifted = source.replace("consolidated", "consolidate")
    rows = [
        verify_claim(
            Claim("fuzzy", "Claim", source=reference, excerpt=drifted),
            resolved(reference, source),
        )
    ]
    metrics = verification_metrics(rows)
    assert rows[0].method == "fuzzy"
    assert rows[0].anchor == "found"
    assert metrics["counts"]["fuzzy_anchored_excerpts"] == 1
    assert metrics["anchor_outcome_counts"]["fuzzy_found"] == 1
    fuzzy = metrics["rates"]["fuzzy_anchor_share"]
    assert (fuzzy["numerator"], fuzzy["denominator"], fuzzy["value"]) == (1, 1, 1.0)


def test_serialized_outcomes_and_metrics_distinguish_all_anchor_methods():
    reference = SourceReference("s1", "https://example.test/a")
    source = "Exact bytes. Mixed Case."
    fuzzy_source = (
        "The company reported consolidated revenue of "
        "$14.2 million for the financial year ending 31 December 2025."
    )
    rows = [
        verify_claim(
            Claim("exact", "Claim", source=reference, excerpt="Exact bytes."),
            resolved(reference, source),
        ),
        verify_claim(
            Claim("normalised", "Claim", source=reference, excerpt="mixed case."),
            resolved(reference, source),
        ),
        verify_claim(
            Claim(
                "fuzzy",
                "Claim",
                source=reference,
                excerpt=(
                    "The company reported consolidate revenue of $14.2 million for "
                    "the financial year ending 31 December 2025."
                ),
            ),
            resolved(reference, fuzzy_source),
        ),
    ]
    assert [row.method for row in rows] == ["byte_exact", "normalised", "fuzzy"]
    assert rows[1].to_dict()["normalisation_reasons"] == ["case"]
    metrics = verification_metrics(rows)
    assert metrics["counts"]["byte_exact_anchored_excerpts"] == 1
    assert metrics["counts"]["normalised_anchored_excerpts"] == 1
    assert metrics["counts"]["fuzzy_anchored_excerpts"] == 1

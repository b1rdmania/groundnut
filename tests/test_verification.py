from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
import pytest

from groundnut.verification import (
    CalculationInput,
    CalculationLineage,
    Claim,
    anchor_excerpt,
    verification_metrics,
    verify_claim,
)


def resolved(reference, text):
    return SourceResolution(
        source=ResolvedSource(
            reference=reference,
            text=text,
            fetched_at="2026-08-17T00:00:00Z",
            status=200,
            media_type="text/plain",
        )
    )


def test_exact_and_format_normalised_excerpt_anchor():
    assert anchor_excerpt("Revenue was $14.2M.", "Revenue was $14.2M.").anchor == "found"
    outcome = anchor_excerpt(
        "REVENUE  WAS  $14.2M — audited", "Revenue was $14.2M - audited"
    )
    assert outcome.anchor == "found"
    assert outcome.method == "exact"


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
    assert metrics["schema"] == "groundnut-verification-metrics/v2"
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
    assert metrics["rates"]["excerpt_anchoring"]["value"] == 1.0
    assert metrics["anchor_outcome_counts"]["no_source"] == 1
    by_class = metrics["by_provenance_class"]["unclassified"]
    assert by_class["citation_coverage"]["denominator"] == 2


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

from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
from groundnut.verification import Claim, anchor_excerpt, verification_metrics, verify_claim


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
    assert metrics["citation_coverage"] == 0.5
    assert metrics["source_accessibility"] == 1.0
    assert metrics["excerpt_anchoring"] == 1.0

import pytest

from groundnut.metrics import MetricEnvelope


def test_metric_envelope_keeps_population_and_arithmetic_together():
    metric = MetricEnvelope(
        name="citation_coverage",
        metric_class="coverage",
        numerator=105,
        denominator=269,
        population="all detected claims",
    )
    payload = metric.to_dict()
    assert payload["schema"] == "groundnut-metric-envelope/v1"
    assert payload["numerator"] == 105
    assert payload["denominator"] == 269
    assert payload["population"] == "all detected claims"
    assert payload["value"] == 105 / 269


def test_metric_envelope_fails_on_impossible_or_unlabelled_population():
    with pytest.raises(ValueError, match="must not exceed"):
        MetricEnvelope("rate", "coverage", 2, 1, "claims")
    with pytest.raises(ValueError, match="population"):
        MetricEnvelope("rate", "coverage", 0, 0, "")

"""Denominator-safe metric contracts for report and gate artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricEnvelope:
    """A rate whose population and arithmetic cannot be separated from it."""

    name: str
    metric_class: str
    numerator: int
    denominator: int
    population: str
    schema: str = "groundnut-metric-envelope/v1"

    def __post_init__(self) -> None:
        if self.schema != "groundnut-metric-envelope/v1":
            raise ValueError(f"unsupported metric envelope schema: {self.schema}")
        if not self.name.strip() or not self.metric_class.strip() or not self.population.strip():
            raise ValueError("metric identity, class, and population are required")
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("metric counts must not be negative")
        if self.numerator > self.denominator:
            raise ValueError("metric numerator must not exceed denominator")

    @property
    def value(self) -> float | None:
        return self.numerator / self.denominator if self.denominator else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "name": self.name,
            "class": self.metric_class,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "population": self.population,
            "value": self.value,
        }

"""Preregisterable support-detector composition for measured bake-offs."""

from __future__ import annotations

from .support import (
    DetectorDecision,
    DetectorIdentity,
    ExactSupportDetector,
    SupportDetector,
    configuration_sha256,
)


class ExactThenFallbackSupportDetector:
    """Keep exact positives; route only exact misses to a frozen detector."""

    def __init__(self, fallback: SupportDetector) -> None:
        self.exact = ExactSupportDetector()
        self.fallback = fallback
        self.identity = self.identity_for(fallback.identity)

    @staticmethod
    def identity_for(fallback: DetectorIdentity) -> DetectorIdentity:
        configuration = {
            "schema": "groundnut-exact-then-fallback/v1",
            "routing": "exact_supported_else_fallback",
            "exact_detector": ExactSupportDetector.identity.canonical_payload(),
            "fallback_detector": fallback.canonical_payload(),
        }
        return DetectorIdentity(
            adapter="groundnut.composed.exact_then_fallback.v1",
            model=f"normalised_substring+{fallback.model}",
            revision="1",
            package="groundnut",
            package_version="1",
            configuration_sha256=configuration_sha256(configuration),
        )

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision:
        exact = self.exact.assess(
            source_text=source_text,
            claim_text=claim_text,
            question=question,
        )
        if exact.label == "supported":
            return DetectorDecision(
                label=exact.label,
                confidence=exact.confidence,
                reason="Exact-first route: normalized claim text occurs in the source.",
                spans=exact.spans,
                raw_output_sha256=exact.raw_output_sha256,
            )
        fallback = self.fallback.assess(
            source_text=source_text,
            claim_text=claim_text,
            question=question,
        )
        return DetectorDecision(
            label=fallback.label,
            confidence=fallback.confidence,
            reason=f"Exact-first route missed; {fallback.reason}",
            spans=fallback.spans,
            raw_output_sha256=fallback.raw_output_sha256,
        )

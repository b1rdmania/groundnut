"""Optional MiniCheck adapter with conservative binary support mapping."""

from __future__ import annotations

from typing import Any

from ..signals import ComponentLicence, ComponentSignal, component_input_sha256
from ..support import (
    DetectorDecision,
    DetectorIdentity,
    configuration_sha256,
)


MINICHECK_CODE_SOURCE = "https://github.com/Liyan06/MiniCheck"


class MiniCheckAdapter:
    """Wrap an injected, revision-pinned MiniCheck scorer.

    MiniCheck's public constructor does not expose an immutable model revision,
    so Groundnut does not instantiate it implicitly. The research runner must
    load pinned weights, then supply the scorer and recorded identity here.
    """

    def __init__(
        self,
        *,
        scorer: Any,
        model: str,
        revision: str,
        installed_package_version: str,
        model_licence_spdx: str = "NOASSERTION",
        model_source: str | None = None,
    ) -> None:
        if scorer is None:
            raise ValueError("MiniCheck adapter requires an injected pinned scorer")
        config = {
            "mapping": "groundnut-minicheck/v1",
            "unsupported_mapping": "insufficient",
        }
        self.identity = DetectorIdentity(
            adapter="groundnut.minicheck.v1",
            model=model,
            revision=revision,
            package="minicheck",
            package_version=installed_package_version,
            configuration_sha256=configuration_sha256(config),
        )
        self.licence = ComponentLicence(
            code_spdx="Apache-2.0",
            code_source=MINICHECK_CODE_SOURCE,
            model_spdx=model_licence_spdx,
            model_source=model_source or model,
        )
        self.scorer = scorer

    def assess(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> DetectorDecision:
        decision, _ = self.assess_with_signal(
            source_text=source_text,
            claim_text=claim_text,
            question=question,
        )
        return decision

    def assess_with_signal(
        self, *, source_text: str, claim_text: str, question: str | None
    ) -> tuple[DetectorDecision, ComponentSignal]:
        result = self.scorer.score(docs=[source_text], claims=[claim_text])
        if not isinstance(result, (tuple, list)) or len(result) < 2:
            raise TypeError("MiniCheck score output must contain labels and probabilities")
        labels, probabilities = result[0], result[1]
        if len(labels) != 1 or len(probabilities) != 1:
            raise ValueError("MiniCheck adapter expected exactly one score")
        label = int(labels[0])
        probability = float(probabilities[0])
        if label not in {0, 1} or not 0.0 <= probability <= 1.0:
            raise ValueError("MiniCheck returned an invalid label or probability")
        supported = label == 1
        normalized = {"label": label, "support_probability": probability}
        reason = (
            "MiniCheck classified the claim as supported."
            if supported
            else "MiniCheck did not establish support; binary output cannot "
            "distinguish contradiction from insufficient evidence."
        )
        signal = ComponentSignal(
            role="unsupported",
            label="supported" if supported else "insufficient",
            scores={
                "support_probability": probability,
                "unsupported_probability": 1.0 - probability,
            },
            input_sha256=component_input_sha256(
                source_text=source_text,
                claim_text=claim_text,
                question=question,
            ),
            component=self.identity,
            licence=self.licence,
            raw_output=normalized,
            note=reason,
        )
        decision = DetectorDecision(
            label="supported" if supported else "insufficient",
            confidence=probability if supported else 1.0 - probability,
            reason=reason,
            raw_output_sha256=signal.raw_output_sha256,
        )
        return decision, signal

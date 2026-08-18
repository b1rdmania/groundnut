"""Typed, replayable component signals for Groundnut's composed engine.

A signal records what one component observed. It is not a support verdict and
does not gain authority when other components agree with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .support import DetectorIdentity


COMPONENT_SIGNAL_SCHEMA = "groundnut-component-signal/v1"
SIGNAL_BUNDLE_SCHEMA = "groundnut-signal-bundle/v1"
SIGNAL_ROLES = {
    "presence",
    "numeric",
    "attribution",
    "relevance",
    "entailment",
    "contradiction",
    "unsupported",
    "span_localisation",
    "segmentation",
    "arena_attack",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def component_input_sha256(
    *, source_text: str, claim_text: str, question: str | None
) -> str:
    """Bind a component signal to the exact semantic input."""
    return _sha256_json(
        {
            "source_text": source_text,
            "claim_text": claim_text,
            "question": question,
        }
    )


@dataclass(frozen=True)
class ComponentLicence:
    """Code and model licence identity recorded at experiment time."""

    code_spdx: str
    code_source: str
    model_spdx: str | None = None
    model_source: str | None = None

    def __post_init__(self) -> None:
        if not self.code_spdx.strip() or not self.code_source.strip():
            raise ValueError("component code licence and source are required")
        if (self.model_spdx is None) != (self.model_source is None):
            raise ValueError("component model licence and source must appear together")
        if self.model_spdx is not None and not self.model_spdx.strip():
            raise ValueError("component model licence must not be empty")
        if self.model_source is not None and not self.model_source.strip():
            raise ValueError("component model source must not be empty")

    def canonical_payload(self) -> dict[str, str | None]:
        return {
            "code_spdx": self.code_spdx,
            "code_source": self.code_source,
            "model_spdx": self.model_spdx,
            "model_source": self.model_source,
        }


@dataclass(frozen=True)
class ComponentSignal:
    """One component's named signal over one exact input."""

    role: str
    label: str
    scores: Mapping[str, float]
    input_sha256: str
    component: DetectorIdentity
    licence: ComponentLicence
    raw_output: Any
    note: str
    schema: str = COMPONENT_SIGNAL_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != COMPONENT_SIGNAL_SCHEMA:
            raise ValueError(f"unsupported component signal schema: {self.schema}")
        if self.role not in SIGNAL_ROLES:
            raise ValueError(f"unknown component signal role: {self.role}")
        if not self.label.strip() or not self.note.strip():
            raise ValueError("component signal label and note are required")
        if not _SHA256.fullmatch(self.input_sha256):
            raise ValueError("component signal input_sha256 must be lowercase SHA-256")
        normalized_scores = {str(key): float(value) for key, value in self.scores.items()}
        if not normalized_scores or any(not key.strip() for key in normalized_scores):
            raise ValueError("component signal requires named scores")
        if any(
            not math.isfinite(value) or value < 0.0 or value > 1.0
            for value in normalized_scores.values()
        ):
            raise ValueError("component signal scores must be between 0 and 1")
        _canonical_json(self.raw_output)
        object.__setattr__(self, "scores", normalized_scores)

    @property
    def raw_output_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.raw_output)).hexdigest()

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "role": self.role,
            "label": self.label,
            "scores": dict(sorted(self.scores.items())),
            "input_sha256": self.input_sha256,
            "component": {
                **self.component.canonical_payload(),
                "sha256": self.component.sha256,
            },
            "licence": self.licence.canonical_payload(),
            "raw_output": self.raw_output,
            "raw_output_sha256": self.raw_output_sha256,
            "note": self.note,
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


@dataclass(frozen=True)
class SignalBundle:
    """Several independent component signals over the same exact input."""

    claim_id: str
    input_sha256: str
    signals: tuple[ComponentSignal, ...] = field(default_factory=tuple)
    schema: str = SIGNAL_BUNDLE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SIGNAL_BUNDLE_SCHEMA:
            raise ValueError(f"unsupported signal bundle schema: {self.schema}")
        if not self.claim_id.strip() or not _SHA256.fullmatch(self.input_sha256):
            raise ValueError("signal bundle requires claim id and lowercase SHA-256")
        ordered = tuple(
            sorted(self.signals, key=lambda row: (row.role, row.component.sha256))
        )
        if not ordered:
            raise ValueError("signal bundle requires at least one signal")
        if any(row.input_sha256 != self.input_sha256 for row in ordered):
            raise ValueError("signal bundle contains a different component input")
        identities = [(row.role, row.component.sha256) for row in ordered]
        if len(identities) != len(set(identities)):
            raise ValueError("signal bundle repeats a component role and identity")
        object.__setattr__(self, "signals", ordered)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "claim_id": self.claim_id,
            "input_sha256": self.input_sha256,
            "signals": [row.to_dict() for row in self.signals],
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise ValueError("component raw output must be finite JSON") from error


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()

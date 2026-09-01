"""Render-bound evidence parity without owning a host renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ArtifactExtraction, ArtifactProfile, DEFAULT_ARTIFACT_PROFILE, extract_artifact
from .receipt import sha256_json


RENDER_RECEIPT_SCHEMA = "groundnut-render-receipt/v1"


def _canonical_sha256(value: Any) -> str:
    return sha256_json(value)


@dataclass(frozen=True)
class RendererIdentity:
    name: str
    version: str
    configuration: Mapping[str, Any]
    _configuration_json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("renderer name and version are required")
        try:
            encoded = json.dumps(
                self.configuration,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("renderer configuration must be canonical JSON") from exc
        object.__setattr__(self, "_configuration_json", encoded)

    @property
    def configuration_sha256(self) -> str:
        return hashlib.sha256(self._configuration_json.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "configuration": json.loads(self._configuration_json),
            "configuration_sha256": self.configuration_sha256,
        }


@dataclass(frozen=True)
class RenderReceipt:
    source: ArtifactExtraction
    rendered: ArtifactExtraction
    source_bytes: int
    rendered_bytes: int
    renderer: RendererIdentity
    evidence_sequence: tuple[tuple[str, str | None, str | None], ...]

    def canonical_payload(self) -> dict[str, Any]:
        sequence = [
            {"source_uri": uri, "excerpt": excerpt, "locator": locator}
            for uri, excerpt, locator in self.evidence_sequence
        ]
        return {
            "schema": RENDER_RECEIPT_SCHEMA,
            "disclosure": (
                "Rendering receipt only. Evidence-sequence parity does not establish "
                "semantic support, truth, publication approval, or recommendation."
            ),
            "source": _artifact_summary(self.source, self.source_bytes),
            "rendered": _artifact_summary(self.rendered, self.rendered_bytes),
            "renderer": self.renderer.to_dict(),
            "parity": {
                "evidence_sequence_identical": True,
                "cited_occurrences": len(sequence),
                "evidence_sequence_sha256": _canonical_sha256(sequence),
                "evidence_sequence": sequence,
            },
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def compare_rendered_artifacts(
    source_path: str | Path,
    rendered_path: str | Path,
    *,
    renderer: RendererIdentity,
    source_profile: ArtifactProfile = DEFAULT_ARTIFACT_PROFILE,
    rendered_profile: ArtifactProfile = DEFAULT_ARTIFACT_PROFILE,
) -> RenderReceipt:
    """Fail unless ordered source URI, excerpt, and locator occurrences survive."""

    source_file = Path(source_path)
    rendered_file = Path(rendered_path)
    source = extract_artifact(source_file, source_profile)
    rendered = extract_artifact(rendered_file, rendered_profile)
    expected = _evidence_sequence(source)
    actual = _evidence_sequence(rendered)
    if expected != actual:
        difference = _first_difference(expected, actual)
        raise ValueError(
            "render evidence parity failed: "
            f"source has {len(expected)} cited occurrences, rendered artifact has "
            f"{len(actual)}; first difference at position {difference}"
        )
    return RenderReceipt(
        source=source,
        rendered=rendered,
        source_bytes=len(source_file.read_bytes()),
        rendered_bytes=len(rendered_file.read_bytes()),
        renderer=renderer,
        evidence_sequence=expected,
    )


def _evidence_sequence(
    extraction: ArtifactExtraction,
) -> tuple[tuple[str, str | None, str | None], ...]:
    return tuple(
        (claim.source.uri, claim.excerpt, claim.locator)
        for claim in extraction.claims
        if claim.source is not None
    )


def _first_difference(left: tuple[Any, ...], right: tuple[Any, ...]) -> int:
    for index, (expected, actual) in enumerate(zip(left, right), 1):
        if expected != actual:
            return index
    return min(len(left), len(right)) + 1


def _artifact_summary(extraction: ArtifactExtraction, size: int) -> dict[str, Any]:
    return {
        "kind": extraction.kind,
        "sha256": extraction.input_sha256,
        "bytes": size,
        "claim_count": len(extraction.claims),
        "cited_claim_count": sum(
            claim.source is not None for claim in extraction.claims
        ),
        "profile": {
            "key": extraction.profile_key,
            "sha256": extraction.profile_sha256,
        },
        "segmenter": extraction.segmenter.to_dict(),
    }

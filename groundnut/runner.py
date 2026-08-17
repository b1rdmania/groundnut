"""Canonical composition surface for one source-bound claim-checking run."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .arena_emission import ArenaEmissionProfile, ArenaTaskEmission, emit_arena_tasks
from .artifacts import ArtifactExtraction, ArtifactProfile, extract_artifact
from .authority import (
    AuthorityDeclaration,
    AuthorityPolicy,
    ClaimEvidenceReport,
    account_for_claim_check,
)
from .checker import check_claims
from .domain import DomainPack
from .run_manifest import (
    ArtifactDigest,
    DomainDigest,
    EngineIdentity,
    PolicyDigest,
    RunManifest,
    RuntimeComponent,
    SourceDigest,
)
from .sources import SnapshotFirstResolver, SourceAcquisition, SourceReference
from .support import SupportDetector, SupportPolicy


@dataclass(frozen=True)
class CanonicalRun:
    artifact: ArtifactExtraction
    acquisitions: tuple[SourceAcquisition, ...]
    evidence: ClaimEvidenceReport
    arena: ArenaTaskEmission | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "acquisitions",
            tuple(
                sorted(
                    self.acquisitions,
                    key=lambda row: (row.reference.source_id, row.reference.uri),
                )
            ),
        )
        claim_sources = {
            claim.source.source_id
            for claim in self.artifact.claims
            if claim.source is not None
        }
        acquisition_sources = {row.reference.source_id for row in self.acquisitions}
        if acquisition_sources != claim_sources:
            raise ValueError("canonical run requires one acquisition per cited source")
        if len(self.evidence.accounts) != len(self.artifact.claims):
            raise ValueError("canonical run evidence differs from artifact claims")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-canonical-run/v1",
            "artifact": self.artifact.to_dict(),
            "acquisitions": [row.to_dict() for row in self.acquisitions],
            "evidence": self.evidence.to_dict(),
            "arena": self.arena.to_dict() if self.arena else None,
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


@dataclass(frozen=True)
class CanonicalExecution:
    run: CanonicalRun
    manifest: RunManifest

    def __post_init__(self) -> None:
        digest = ArtifactDigest.from_value("canonical_run", self.run.to_dict())
        if digest not in self.manifest.artifacts:
            raise ValueError("execution manifest does not bind the canonical run")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-canonical-execution/v1",
            "run": self.run.to_dict(),
            "manifest": self.manifest.to_dict(),
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def run_canonical_check(
    artifact_path: str | Path,
    *,
    artifact_profile: ArtifactProfile,
    resolver: SnapshotFirstResolver,
    detector: SupportDetector,
    support_policy: SupportPolicy,
    authority_policy: AuthorityPolicy,
    authority_declarations: Mapping[str, AuthorityDeclaration] | None = None,
    arena_profile: ArenaEmissionProfile | None = None,
    arena_artifact_path: str | Path | None = None,
) -> CanonicalRun:
    artifact = extract_artifact(artifact_path, artifact_profile)
    references = sorted(
        {claim.source for claim in artifact.claims if claim.source is not None},
        key=lambda row: (row.source_id, row.uri),
    )
    acquisitions = tuple(resolver.acquire(reference) for reference in references)
    resolutions = {
        reference: acquisition.resolution
        for reference, acquisition in zip(references, acquisitions, strict=True)
    }
    checked = check_claims(
        artifact.claims,
        resolutions,
        detector=detector,
        policy=support_policy,
    )
    evidence = account_for_claim_check(
        checked,
        policy=authority_policy,
        declarations=authority_declarations,
    )
    arena = (
        emit_arena_tasks(arena_artifact_path or artifact_path, arena_profile)
        if arena_profile is not None
        else None
    )
    return CanonicalRun(
        artifact=artifact,
        acquisitions=acquisitions,
        evidence=evidence,
        arena=arena,
    )


def execute_canonical_check(
    artifact_path: str | Path,
    *,
    engine: EngineIdentity,
    domain: DomainPack,
    artifact_profile: ArtifactProfile,
    resolver: SnapshotFirstResolver,
    detector: SupportDetector,
    support_policy: SupportPolicy,
    authority_policy: AuthorityPolicy,
    authority_declarations: Mapping[str, AuthorityDeclaration] | None = None,
    arena_profile: ArenaEmissionProfile | None = None,
    arena_artifact_path: str | Path | None = None,
    publication_grade: bool = False,
) -> CanonicalExecution:
    if publication_grade:
        engine.require_publishable()
    run = run_canonical_check(
        artifact_path,
        artifact_profile=artifact_profile,
        resolver=resolver,
        detector=detector,
        support_policy=support_policy,
        authority_policy=authority_policy,
        authority_declarations=authority_declarations,
        arena_profile=arena_profile,
        arena_artifact_path=arena_artifact_path,
    )
    sources = tuple(
        SourceDigest.from_record(
            acquisition.resolution.source.record,
            snapshot_sha256=acquisition.snapshot_sha256,
        )
        for acquisition in run.acquisitions
        if acquisition.resolution.source is not None
    )
    policies = [
        PolicyDigest.from_policy("artifact_profile", artifact_profile),
        PolicyDigest.from_policy("support", support_policy),
        PolicyDigest.from_policy("authority", authority_policy),
    ]
    if arena_profile is not None:
        policies.append(PolicyDigest.from_policy("arena_emission", arena_profile))
    identity = detector.identity
    component = RuntimeComponent.from_config(
        role="semantic_support_detector",
        name=f"{identity.adapter}:{identity.model}",
        revision=identity.revision,
        configuration=identity.canonical_payload(),
    )
    manifest = RunManifest(
        engine=engine,
        domain=DomainDigest.from_pack(domain),
        sources=sources,
        policies=tuple(policies),
        components=(component,),
        artifacts=(ArtifactDigest.from_value("canonical_run", run.to_dict()),),
    )
    return CanonicalExecution(run=run, manifest=manifest)

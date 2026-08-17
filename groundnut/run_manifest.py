"""Deterministic provenance manifest for one canonical Groundnut run."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .domain import DomainPack
from .provenance import SourceRecord


RUN_SCHEMA = "groundnut-run-manifest/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MOVING_REVISIONS = {"main", "master", "latest", "head"}


@dataclass(frozen=True)
class EngineIdentity:
    version: str
    revision: str
    package: str = "groundnut"

    def __post_init__(self) -> None:
        _require_text(self.package, self.version, self.revision)
        _require_immutable_revision(self.revision)

    def to_dict(self) -> dict[str, str]:
        return {
            "package": self.package,
            "version": self.version,
            "revision": self.revision,
        }


@dataclass(frozen=True)
class DomainDigest:
    key: str
    version: str
    playbook_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.key, self.version)
        _require_sha256(self.playbook_sha256, "playbook_sha256")
        _require_sha256(self.manifest_sha256, "manifest_sha256")

    @classmethod
    def from_pack(cls, domain: DomainPack) -> "DomainDigest":
        return cls(
            key=domain.key,
            version=domain.version,
            playbook_sha256=domain.playbook_sha256,
            manifest_sha256=domain.manifest_sha256,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "version": self.version,
            "playbook_sha256": self.playbook_sha256,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class SourceDigest:
    source_id: str
    sha256: str
    characters: int
    snapshot_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_id)
        _require_sha256(self.sha256, "source sha256")
        if self.characters < 0:
            raise ValueError("source character count must not be negative")
        if self.snapshot_sha256 is not None:
            _require_sha256(self.snapshot_sha256, "snapshot_sha256")

    @classmethod
    def from_record(
        cls, record: SourceRecord, *, snapshot_sha256: str | None = None
    ) -> "SourceDigest":
        return cls(
            source_id=record.source_id,
            sha256=record.sha256,
            characters=record.characters,
            snapshot_sha256=snapshot_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "sha256": self.sha256,
            "characters": self.characters,
            "snapshot_sha256": self.snapshot_sha256,
        }


@dataclass(frozen=True)
class PolicyDigest:
    kind: str
    key: str
    sha256: str

    def __post_init__(self) -> None:
        _require_text(self.kind, self.key)
        _require_sha256(self.sha256, "policy sha256")

    @classmethod
    def from_policy(cls, kind: str, policy: Any) -> "PolicyDigest":
        return cls(kind=kind, key=str(policy.key), sha256=str(policy.sha256))

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "key": self.key, "sha256": self.sha256}


@dataclass(frozen=True)
class RuntimeComponent:
    role: str
    name: str
    revision: str
    configuration_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.role, self.name, self.revision)
        _require_immutable_revision(self.revision)
        _require_sha256(self.configuration_sha256, "configuration_sha256")

    @classmethod
    def from_config(
        cls,
        *,
        role: str,
        name: str,
        revision: str,
        configuration: Mapping[str, Any],
    ) -> "RuntimeComponent":
        return cls(
            role=role,
            name=name,
            revision=revision,
            configuration_sha256=_sha256_json(configuration),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "name": self.name,
            "revision": self.revision,
            "configuration_sha256": self.configuration_sha256,
        }


@dataclass(frozen=True)
class ArtifactDigest:
    kind: str
    schema: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        _require_text(self.kind, self.schema)
        _require_sha256(self.sha256, "artifact sha256")
        if self.bytes < 0:
            raise ValueError("artifact byte count must not be negative")

    @classmethod
    def from_value(cls, kind: str, value: Mapping[str, Any]) -> "ArtifactDigest":
        schema = value.get("schema")
        if not isinstance(schema, str) or not schema.strip():
            raise ValueError("manifest artifact must declare a schema")
        encoded = _canonical_json(value)
        return cls(
            kind=kind,
            schema=schema,
            sha256=hashlib.sha256(encoded).hexdigest(),
            bytes=len(encoded),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schema": self.schema,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


@dataclass(frozen=True)
class RunManifest:
    engine: EngineIdentity
    domain: DomainDigest
    sources: tuple[SourceDigest, ...]
    policies: tuple[PolicyDigest, ...]
    components: tuple[RuntimeComponent, ...]
    artifacts: tuple[ArtifactDigest, ...]
    schema: str = RUN_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sources", tuple(sorted(self.sources, key=lambda row: row.source_id))
        )
        object.__setattr__(
            self,
            "policies",
            tuple(sorted(self.policies, key=lambda row: (row.kind, row.key))),
        )
        object.__setattr__(
            self,
            "components",
            tuple(sorted(self.components, key=lambda row: (row.role, row.name))),
        )
        object.__setattr__(
            self,
            "artifacts",
            tuple(sorted(self.artifacts, key=lambda row: (row.kind, row.sha256))),
        )
        if self.schema != RUN_SCHEMA:
            raise ValueError(f"unsupported run-manifest schema: {self.schema}")
        if not self.sources or not self.artifacts:
            raise ValueError("run manifest requires at least one source and artifact")
        _require_unique("source", [row.source_id for row in self.sources])
        _require_unique("policy", [(row.kind, row.key) for row in self.policies])
        _require_unique(
            "component", [(row.role, row.name) for row in self.components]
        )
        _require_unique(
            "artifact", [(row.kind, row.sha256) for row in self.artifacts]
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "engine": self.engine.to_dict(),
            "domain": self.domain.to_dict(),
            "sources": [row.to_dict() for row in self.sources],
            "policies": [row.to_dict() for row in self.policies],
            "components": [row.to_dict() for row in self.components],
            "artifacts": [row.to_dict() for row in self.artifacts],
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_text(*values: str) -> None:
    if not all(value.strip() for value in values):
        raise ValueError("manifest identity fields must not be empty")


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_immutable_revision(value: str) -> None:
    if value.casefold() in _MOVING_REVISIONS:
        raise ValueError("manifest revision must be immutable, not a moving ref")


def _require_unique(label: str, values: list[Any]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate run-manifest {label}")

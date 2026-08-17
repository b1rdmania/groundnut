"""Deterministic provenance manifest for one canonical Groundnut run."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from .domain import DomainPack
from .provenance import SourceRecord


RUN_SCHEMA = "groundnut-run-manifest/v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MOVING_REVISIONS = {"main", "master", "latest", "head"}


@dataclass(frozen=True)
class EngineIdentity:
    version: str
    revision: str
    source_sha256: str
    dirty: bool
    package: str = "groundnut"

    def __post_init__(self) -> None:
        _require_text(self.package, self.version, self.revision)
        _require_immutable_revision(self.revision)
        _require_sha256(self.source_sha256, "engine source_sha256")
        if not isinstance(self.dirty, bool):
            raise ValueError("engine dirty state must be boolean")

    @classmethod
    def from_source_tree(
        cls,
        *,
        version: str,
        revision: str,
        source_root: str | Path,
        dirty: bool,
        package: str = "groundnut",
    ) -> "EngineIdentity":
        return cls(
            package=package,
            version=version,
            revision=revision,
            source_sha256=source_tree_sha256(source_root),
            dirty=dirty,
        )

    @classmethod
    def from_repository(
        cls,
        *,
        version: str,
        repository: str | Path,
        source_directory: str = "groundnut",
        package: str = "groundnut",
    ) -> "EngineIdentity":
        root = Path(repository).resolve()
        source_root = (root / source_directory).resolve()
        try:
            source_root.relative_to(root)
        except ValueError as exc:
            raise ValueError("engine source directory must be inside repository") from exc
        revision = _git(root, "rev-parse", "HEAD")
        relative_source = source_root.relative_to(root).as_posix()
        dirty = bool(
            _git(
                root,
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                relative_source,
            )
        )
        return cls.from_source_tree(
            package=package,
            version=version,
            revision=revision,
            source_root=source_root,
            dirty=dirty,
        )

    @property
    def publishable(self) -> bool:
        return not self.dirty

    def require_publishable(self) -> None:
        if self.dirty:
            raise ValueError("publication-grade runs require a clean engine build")

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "version": self.version,
            "revision": self.revision,
            "source_sha256": self.source_sha256,
            "dirty": self.dirty,
            "publishable": self.publishable,
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


def source_tree_sha256(source_root: str | Path) -> str:
    """Hash shipped Python sources with path and length framing."""
    root = Path(source_root)
    if not root.is_dir():
        raise ValueError("engine source root must be a directory")
    files = sorted(
        (
            path
            for path in root.rglob("*.py")
            if path.is_file() and "__pycache__" not in path.parts
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not files:
        raise ValueError("engine source root contains no Python sources")
    digest = hashlib.sha256(b"groundnut-source-tree/v1\0")
    for path in files:
        name = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _git(repository: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("engine repository identity is unavailable") from exc


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

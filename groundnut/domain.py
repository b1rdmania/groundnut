"""Versioned domain packs: change the checklist, change the job.

A domain pack contains job-specific vocabulary and prompt framing. The engine
owns segmentation, model invocation, grounding, provenance, and evaluation
interfaces. A pack's evidence status says how far its quality has actually
been tested; configuration portability is not evidence portability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


PACK_SCHEMA = "groundnut-domain/v1"
EVIDENCE_STATUSES = {
    "experimental",
    "development",
    "holdout_qualified",
    "production_approved",
}
_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def _require_key(value: str, label: str) -> None:
    if not _KEY.fullmatch(value):
        raise ValueError(f"{label} must match {_KEY.pattern}: {value!r}")


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    severity: int
    description: str = ""

    def __post_init__(self) -> None:
        _require_key(self.key, "category key")
        if not self.name.strip():
            raise ValueError("category name must not be empty")
        if not 1 <= self.severity <= 5:
            raise ValueError("category severity must be between 1 and 5")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Category":
        return cls(
            key=str(value["key"]),
            name=str(value["name"]),
            severity=int(value["severity"]),
            description=str(value.get("description", "")),
        )


@dataclass(frozen=True)
class DocumentType:
    key: str
    name: str
    description: str = ""

    def __post_init__(self) -> None:
        _require_key(self.key, "document type key")
        if not self.name.strip():
            raise ValueError("document type name must not be empty")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DocumentType":
        return cls(
            key=str(value["key"]),
            name=str(value["name"]),
            description=str(value.get("description", "")),
        )


@dataclass(frozen=True)
class DomainEvidence:
    status: str = "experimental"
    dataset: str | None = None
    disclosure: str = "No domain-specific quality claim has been established."

    def __post_init__(self) -> None:
        if self.status not in EVIDENCE_STATUSES:
            raise ValueError(f"unknown evidence status: {self.status}")
        if not self.disclosure.strip():
            raise ValueError("evidence disclosure must not be empty")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "DomainEvidence":
        if value is None:
            return cls()
        return cls(
            status=str(value.get("status", "experimental")),
            dataset=str(value["dataset"]) if value.get("dataset") else None,
            disclosure=str(
                value.get(
                    "disclosure",
                    "No domain-specific quality claim has been established.",
                )
            ),
        )


@dataclass(frozen=True)
class DomainPack:
    key: str
    version: str
    name: str
    document_noun: str
    extract_context: str
    classify_context: str
    categories: tuple[Category, ...]
    document_types: tuple[DocumentType, ...] = field(default_factory=tuple)
    evidence: DomainEvidence = field(default_factory=DomainEvidence)
    schema: str = PACK_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(self, "document_types", tuple(self.document_types))
        if self.schema != PACK_SCHEMA:
            raise ValueError(f"unsupported domain-pack schema: {self.schema}")
        _require_key(self.key, "domain key")
        if not self.version.strip() or not self.name.strip():
            raise ValueError("domain version and name must not be empty")
        if not self.document_noun.strip():
            raise ValueError("document_noun must not be empty")
        if not self.extract_context.strip() or not self.classify_context.strip():
            raise ValueError("domain prompt contexts must not be empty")
        if not self.categories:
            raise ValueError("domain pack must define at least one category")
        self._require_unique("category keys", [c.key for c in self.categories])
        self._require_unique("category names", [c.name for c in self.categories])
        self._require_unique(
            "document type keys", [d.key for d in self.document_types]
        )

    @staticmethod
    def _require_unique(label: str, values: list[str]) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"domain pack contains duplicate {label}")

    @property
    def category_names(self) -> list[str]:
        return [category.name for category in self.categories]

    def category_block(self) -> str:
        return "\n".join(
            f"- {category.name}: {category.description}"
            if category.description
            else f"- {category.name}"
            for category in self.categories
        )

    def document_type_block(self) -> str:
        return "\n".join(
            f"- {doc.key} ({doc.name}): {doc.description}"
            if doc.description
            else f"- {doc.key} ({doc.name})"
            for doc in self.document_types
        )

    def playbook_payload(self) -> dict[str, Any]:
        """The executable job definition, excluding evidence claims."""
        return {
            "schema": self.schema,
            "key": self.key,
            "version": self.version,
            "name": self.name,
            "document_noun": self.document_noun,
            "extract_context": self.extract_context,
            "classify_context": self.classify_context,
            "categories": [
                {
                    "key": c.key,
                    "name": c.name,
                    "severity": c.severity,
                    "description": c.description,
                }
                for c in self.categories
            ],
            "document_types": [
                {"key": d.key, "name": d.name, "description": d.description}
                for d in self.document_types
            ],
        }

    def canonical_payload(self) -> dict[str, Any]:
        """The complete pack manifest, including its evidence disclosure."""
        return {
            **self.playbook_payload(),
            "evidence": {
                "status": self.evidence.status,
                "dataset": self.evidence.dataset,
                "disclosure": self.evidence.disclosure,
            },
        }

    @property
    def playbook_sha256(self) -> str:
        encoded = json.dumps(
            self.playbook_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def manifest_sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DomainPack":
        return cls(
            schema=str(value.get("schema", PACK_SCHEMA)),
            key=str(value["key"]),
            version=str(value["version"]),
            name=str(value["name"]),
            document_noun=str(value["document_noun"]),
            extract_context=str(value["extract_context"]),
            classify_context=str(value["classify_context"]),
            categories=tuple(
                Category.from_mapping(row) for row in value.get("categories", [])
            ),
            document_types=tuple(
                DocumentType.from_mapping(row)
                for row in value.get("document_types", [])
            ),
            evidence=DomainEvidence.from_mapping(value.get("evidence")),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "DomainPack":
        return cls.from_mapping(json.loads(Path(path).read_text()))

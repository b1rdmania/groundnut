"""Portable, reviewable annotation records for external workbenches."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .provenance import sha256_text
from .support_cases import CaseProvenance
from .support_seeds import AttestedSpanSeed


ANNOTATION_SCHEMA = "groundnut-evidence-annotation/v1"
CREATOR_KINDS = {"human", "dataset", "analyzer", "agent"}
REVIEW_STATES = {"candidate", "accepted", "rejected"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EvidenceAnnotation:
    annotation_id: str
    source_id: str
    source_sha256: str
    start: int
    end: int
    text: str
    label: str
    question: str
    creator_kind: str
    creator_id: str
    review_state: str
    reviewer_ids: tuple[str, ...] = ()
    relationship_ids: tuple[str, ...] = ()
    schema: str = ANNOTATION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewer_ids", tuple(self.reviewer_ids))
        object.__setattr__(self, "relationship_ids", tuple(self.relationship_ids))
        if self.schema != ANNOTATION_SCHEMA:
            raise ValueError(f"unsupported annotation schema: {self.schema}")
        if self.creator_kind not in CREATOR_KINDS:
            raise ValueError(f"unknown annotation creator kind: {self.creator_kind}")
        if self.review_state not in REVIEW_STATES:
            raise ValueError(f"unknown annotation review state: {self.review_state}")
        if self.review_state == "accepted" and not self.reviewer_ids and self.creator_kind != "human":
            raise ValueError("accepted non-human annotations require a human reviewer")
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("annotation source hash must be lowercase SHA-256")
        if not all(
            value.strip()
            for value in (
                self.annotation_id,
                self.source_id,
                self.text,
                self.label,
                self.question,
                self.creator_id,
            )
        ):
            raise ValueError("annotation identity and text fields are required")
        if self.start < 0 or self.end <= self.start or len(self.text) != self.end - self.start:
            raise ValueError("annotation offsets must describe its non-empty text")

    def validate_source(self, source_text: str) -> None:
        if sha256_text(source_text) != self.source_sha256:
            raise ValueError(f"annotation source hash mismatch: {self.annotation_id}")
        if source_text[self.start : self.end] != self.text:
            raise ValueError(f"annotation span mismatch: {self.annotation_id}")

    def to_attested_seed(self) -> AttestedSpanSeed:
        if self.review_state != "accepted":
            raise ValueError("only accepted annotations can become support seeds")
        return AttestedSpanSeed(
            seed_id=self.annotation_id,
            source_id=self.source_id,
            source_sha256=self.source_sha256,
            original_start=self.start,
            original_end=self.end,
            original_text=self.text,
            question=self.question,
            provenance=CaseProvenance(
                kind="attested",
                source="annotation-interchange",
                source_record_id=self.annotation_id,
                method=f"{self.creator_kind}:{self.label}",
                reviewed_by=self.reviewer_ids,
            ),
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "annotation_id": self.annotation_id,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "label": self.label,
            "question": self.question,
            "creator": {"kind": self.creator_kind, "id": self.creator_id},
            "review": {"state": self.review_state, "reviewer_ids": list(self.reviewer_ids)},
            "relationship_ids": list(self.relationship_ids),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceAnnotation":
        creator = value.get("creator")
        review = value.get("review")
        if not isinstance(creator, Mapping) or not isinstance(review, Mapping):
            raise ValueError("annotation creator and review objects are required")
        return cls(
            schema=str(value.get("schema", ANNOTATION_SCHEMA)),
            annotation_id=str(value["annotation_id"]),
            source_id=str(value["source_id"]),
            source_sha256=str(value["source_sha256"]),
            start=int(value["start"]),
            end=int(value["end"]),
            text=str(value["text"]),
            label=str(value["label"]),
            question=str(value["question"]),
            creator_kind=str(creator["kind"]),
            creator_id=str(creator["id"]),
            review_state=str(review["state"]),
            reviewer_ids=tuple(str(item) for item in review.get("reviewer_ids", ())),
            relationship_ids=tuple(str(item) for item in value.get("relationship_ids", ())),
        )


@dataclass(frozen=True)
class AnnotationBundle:
    annotations: tuple[EvidenceAnnotation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "annotations", tuple(self.annotations))
        ids = [row.annotation_id for row in self.annotations]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("annotation bundle requires unique annotations")
        known = set(ids)
        for row in self.annotations:
            missing = set(row.relationship_ids) - known
            if missing:
                raise ValueError(f"annotation {row.annotation_id} has unknown relationships: {sorted(missing)}")

    @property
    def sha256(self) -> str:
        payload = [row.canonical_payload() for row in sorted(self.annotations, key=lambda item: item.annotation_id)]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_jsonl(cls, text: str) -> "AnnotationBundle":
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError("expected object")
                rows.append(EvidenceAnnotation.from_mapping(value))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"annotation JSONL line {number}: {error}") from error
        return cls(tuple(rows))

    def to_jsonl(self) -> str:
        return "".join(
            json.dumps(row.canonical_payload(), sort_keys=True) + "\n"
            for row in sorted(self.annotations, key=lambda item: item.annotation_id)
        )

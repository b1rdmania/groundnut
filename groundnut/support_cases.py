"""Paired, source-anchored cases for detector-transfer measurement.

The case format makes two validity requirements structural: every class in a
group uses the same original source span and therefore the same context window;
and both supported/unsupported classes contain one present and one absent claim,
so exact substring matching cannot separate the labels perfectly.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .provenance import sha256_text
from .support_eval import SupportGold


CASE_SCHEMA = "groundnut-support-case/v3"
CASE_KINDS = {
    "verbatim_supported": "supported",
    "paraphrase_supported": "supported",
    "contradicted": "contradicted",
    "present_irrelevant": "insufficient",
}
PROVENANCE_KINDS = {
    "attested",
    "adjudicated",
    "derived",
    "authored",
    "model_authored",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CaseProvenance:
    """Why a support-case label exists and who has accepted it.

    `attested` covers imported expert annotations, `adjudicated` covers a new
    human ruling made for Groundnut, `derived` covers a recorded deterministic
    transform, and authored cases distinguish human and model authorship.
    Model-authored and adjudicated cases cannot enter a probe without a human
    reviewer recorded here.
    """

    kind: str
    source: str
    source_record_id: str
    method: str
    parent_case_ids: tuple[str, ...] = ()
    reviewed_by: tuple[str, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_case_ids", tuple(self.parent_case_ids))
        object.__setattr__(self, "reviewed_by", tuple(self.reviewed_by))
        if self.kind not in PROVENANCE_KINDS:
            raise ValueError(f"unknown support-case provenance kind: {self.kind}")
        if not all(value.strip() for value in (self.source, self.source_record_id, self.method)):
            raise ValueError("support-case provenance source, record, and method are required")
        if any(not value.strip() for value in self.parent_case_ids + self.reviewed_by):
            raise ValueError("support-case provenance identifiers cannot be blank")
        if self.kind == "derived" and not self.parent_case_ids:
            raise ValueError("derived support cases require at least one parent case")
        if self.kind == "model_authored" and not self.reviewed_by:
            raise ValueError("model-authored support cases require human review")
        if self.kind == "adjudicated" and not self.reviewed_by:
            raise ValueError("adjudicated support cases require human review")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "source_record_id": self.source_record_id,
            "method": self.method,
            "parent_case_ids": list(self.parent_case_ids),
            "reviewed_by": list(self.reviewed_by),
            "note": self.note,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CaseProvenance":
        return cls(
            kind=str(value["kind"]),
            source=str(value["source"]),
            source_record_id=str(value["source_record_id"]),
            method=str(value["method"]),
            parent_case_ids=tuple(str(item) for item in value.get("parent_case_ids", ())),
            reviewed_by=tuple(str(item) for item in value.get("reviewed_by", ())),
            note=None if value.get("note") is None else str(value["note"]),
        )


@dataclass(frozen=True)
class SupportCase:
    case_id: str
    group_id: str
    kind: str
    expected_status: str
    source_id: str
    source_sha256: str
    original_start: int
    original_end: int
    original_text: str
    question: str
    claim_text: str
    present_start: int | None
    present_end: int | None
    provenance: CaseProvenance
    schema: str = CASE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CASE_SCHEMA:
            raise ValueError(f"unsupported support-case schema: {self.schema}")
        if not all(
            value.strip()
            for value in (
                self.case_id,
                self.group_id,
                self.source_id,
                self.original_text,
                self.question,
                self.claim_text,
            )
        ):
            raise ValueError("support-case identity and text fields are required")
        expected = CASE_KINDS.get(self.kind)
        if expected is None:
            raise ValueError(f"unknown support-case kind: {self.kind}")
        if self.expected_status != expected:
            raise ValueError(
                f"{self.kind} case must expect {expected}, not {self.expected_status}"
            )
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("support-case source_sha256 must be lowercase SHA-256")
        if self.original_start < 0 or self.original_end <= self.original_start:
            raise ValueError("support-case original offsets must be non-empty")
        if len(self.original_text) != self.original_end - self.original_start:
            raise ValueError("support-case original text length does not match offsets")
        present = self.kind in {"verbatim_supported", "present_irrelevant"}
        if present != (self.present_start is not None and self.present_end is not None):
            raise ValueError(
                "present support cases require claim offsets; absent cases forbid them"
            )
        if present:
            assert self.present_start is not None and self.present_end is not None
            if (
                self.present_start < 0
                or self.present_end <= self.present_start
                or len(self.claim_text) != self.present_end - self.present_start
            ):
                raise ValueError("support-case claim offsets must describe its exact text")
        if self.kind == "verbatim_supported" and self.claim_text != self.original_text:
            raise ValueError("verbatim_supported claim must equal the original span")
        if self.kind == "verbatim_supported" and (
            self.present_start != self.original_start
            or self.present_end != self.original_end
        ):
            raise ValueError("verbatim_supported claim offsets must equal original offsets")
        if self.kind == "verbatim_supported" and self.provenance.kind != "attested":
            raise ValueError("verbatim_supported cases require attested provenance")
        if self.kind == "contradicted" and self.provenance.kind != "derived":
            raise ValueError("contradicted cases require derived provenance")
        if self.kind == "paraphrase_supported" and self.provenance.kind not in {
            "authored",
            "model_authored",
        }:
            raise ValueError("paraphrase_supported cases require authored provenance")
        if self.kind == "present_irrelevant" and self.provenance.kind != "adjudicated":
            raise ValueError("present_irrelevant cases require adjudicated provenance")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "case_id": self.case_id,
            "group_id": self.group_id,
            "kind": self.kind,
            "expected_status": self.expected_status,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "original_start": self.original_start,
            "original_end": self.original_end,
            "original_text": self.original_text,
            "question": self.question,
            "claim_text": self.claim_text,
            "present_start": self.present_start,
            "present_end": self.present_end,
            "provenance": self.provenance.canonical_payload(),
            "lexical_overlap": self.lexical_overlap,
        }

    @property
    def lexical_overlap(self) -> float:
        """Order-insensitive token Jaccard, recorded to expose easy paraphrases."""
        original = set(re.findall(r"\w+", self.original_text.casefold()))
        claim = set(re.findall(r"\w+", self.claim_text.casefold()))
        union = original | claim
        return 1.0 if not union else round(len(original & claim) / len(union), 6)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SupportCase":
        return cls(
            schema=str(value.get("schema", CASE_SCHEMA)),
            case_id=str(value["case_id"]),
            group_id=str(value["group_id"]),
            kind=str(value["kind"]),
            expected_status=str(value["expected_status"]),
            source_id=str(value["source_id"]),
            source_sha256=str(value["source_sha256"]),
            original_start=int(value["original_start"]),
            original_end=int(value["original_end"]),
            original_text=str(value["original_text"]),
            question=str(value["question"]),
            claim_text=str(value["claim_text"]),
            present_start=(
                None if value.get("present_start") is None else int(value["present_start"])
            ),
            present_end=(
                None if value.get("present_end") is None else int(value["present_end"])
            ),
            provenance=CaseProvenance.from_mapping(value["provenance"]),
        )

    def validate_source(self, source_text: str) -> None:
        if sha256_text(source_text) != self.source_sha256:
            raise ValueError(f"source hash mismatch for case {self.case_id}")
        if source_text[self.original_start : self.original_end] != self.original_text:
            raise ValueError(f"original span mismatch for case {self.case_id}")
        if self.present_start is not None and self.present_end is not None:
            if source_text[self.present_start : self.present_end] != self.claim_text:
                raise ValueError(f"present claim span mismatch for case {self.case_id}")
        elif self.claim_text in source_text:
            raise ValueError(f"{self.kind} claim must be absent in source: {self.case_id}")
        if self.kind == "present_irrelevant" and self.claim_text == self.original_text:
            raise ValueError("present_irrelevant claim cannot equal the original span")

    def context_window(self, source_text: str, max_characters: int) -> str:
        self.validate_source(source_text)
        span_length = self.original_end - self.original_start
        if max_characters < span_length:
            raise ValueError("context window cannot be shorter than original span")
        if len(source_text) <= max_characters:
            return source_text
        spare = max_characters - span_length
        start = max(0, self.original_start - spare // 2)
        end = min(len(source_text), start + max_characters)
        start = max(0, end - max_characters)
        return source_text[start:end]


@dataclass(frozen=True)
class SupportProbe:
    cases: tuple[SupportCase, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", tuple(self.cases))
        if not self.cases:
            raise ValueError("support probe must contain at least one case group")
        _require_unique("case", [case.case_id for case in self.cases])
        groups: dict[str, list[SupportCase]] = {}
        for case in self.cases:
            groups.setdefault(case.group_id, []).append(case)
        for group_id, cases in groups.items():
            kinds = {case.kind for case in cases}
            if kinds != set(CASE_KINDS):
                missing = sorted(set(CASE_KINDS) - kinds)
                extra = sorted(kinds - set(CASE_KINDS))
                raise ValueError(
                    f"support group {group_id} must contain exactly four kinds; "
                    f"missing={missing}, extra={extra}"
                )
            if len(cases) != len(CASE_KINDS):
                raise ValueError(f"support group {group_id} contains duplicate kinds")
            origin = _origin(cases[0])
            if any(_origin(case) != origin for case in cases[1:]):
                raise ValueError(
                    f"support group {group_id} does not share one source span and question"
                )

    @property
    def sha256(self) -> str:
        payload = [
            case.canonical_payload() for case in sorted(self.cases, key=lambda row: row.case_id)
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def group_count(self) -> int:
        return len({case.group_id for case in self.cases})

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "SupportProbe":
        cases = []
        for number, line in enumerate(Path(path).read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError("expected object")
                cases.append(SupportCase.from_mapping(value))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"{path}:{number}: invalid support case: {error}") from error
        return cls(tuple(cases))

    def validate_sources(self, sources: Mapping[str, str]) -> None:
        for case in self.cases:
            try:
                source_text = sources[case.source_id]
            except KeyError as error:
                raise ValueError(f"missing source for case {case.case_id}") from error
            case.validate_source(source_text)

    def contexts(
        self, sources: Mapping[str, str], max_characters: int
    ) -> dict[str, str]:
        self.validate_sources(sources)
        contexts = {}
        groups: dict[str, list[SupportCase]] = {}
        for case in self.cases:
            groups.setdefault(case.group_id, []).append(case)
        for cases in groups.values():
            exemplar = cases[0]
            irrelevant = next(
                case for case in cases if case.kind == "present_irrelevant"
            )
            assert irrelevant.present_start is not None
            assert irrelevant.present_end is not None
            start = min(exemplar.original_start, irrelevant.present_start)
            end = max(exemplar.original_end, irrelevant.present_end)
            context = _bounded_window(
                sources[exemplar.source_id], start, end, max_characters
            )
            if irrelevant.claim_text not in context or exemplar.original_text not in context:
                raise ValueError(
                    f"support group {exemplar.group_id} present spans do not fit "
                    "inside the frozen context window"
                )
            for case in cases:
                contexts[case.case_id] = context
        return contexts

    def gold(self) -> tuple[SupportGold, ...]:
        return tuple(
            SupportGold(case.case_id, case.expected_status, case.kind)
            for case in self.cases
        )


def _origin(case: SupportCase) -> tuple[Any, ...]:
    return (
        case.source_id,
        case.source_sha256,
        case.original_start,
        case.original_end,
        case.original_text,
        case.question,
    )


def _bounded_window(source_text: str, start: int, end: int, max_characters: int) -> str:
    required = end - start
    if max_characters < required:
        raise ValueError(
            "context window cannot contain both original and irrelevant claim spans"
        )
    if len(source_text) <= max_characters:
        return source_text
    spare = max_characters - required
    window_start = max(0, start - spare // 2)
    window_end = min(len(source_text), window_start + max_characters)
    window_start = max(0, window_end - max_characters)
    return source_text[window_start:window_end]


def context_digests_sha256(
    rows: Iterable[tuple[str, str, int]],
) -> str:
    """Hash the ordered case-id/context-digest manifest used by a probe run."""
    payload = [
        {"case_id": case_id, "sha256": digest, "characters": characters}
        for case_id, digest, characters in sorted(rows)
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def contexts_sha256(contexts: Mapping[str, str]) -> str:
    """Hash the exact context text each frozen case will receive."""
    return context_digests_sha256(
        (case_id, sha256_text(text), len(text))
        for case_id, text in contexts.items()
    )


def _require_unique(label: str, values: Iterable[str]) -> None:
    values = tuple(values)
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate support {label} id")

"""Human-review boundary for constructing a canonical support pilot."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import hashlib
import io
import json
from pathlib import Path
import random
import re
from typing import Any, Iterable, Mapping

from .provenance import sha256_text
from .support_cases import (
    CASE_KINDS,
    CaseProvenance,
    SupportCase,
    SupportProbe,
    contexts_sha256,
)
from .support_seeds import AttestedSpanSeed, PresentIrrelevantCandidate


REVIEW_SCHEMA = "groundnut-support-pilot-review/v1"
REVIEW_MANIFEST_SCHEMA = "groundnut-support-pilot-review-manifest/v1"
DECISIONS = {"pending", "accepted", "rejected", "ambiguous"}
AUTHOR_KINDS = {"human", "agent"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NEGATION_PATTERNS = (
    (re.compile(r"\b(shall|must|will|should|may|can)\s+not\b", re.I), r"\1"),
    (re.compile(r"\b(is|are|was|were|has|have|had)\s+not\b", re.I), r"\1"),
    (re.compile(r"\b(shall|must|will|should|may|can)\b", re.I), r"\1 not"),
    (re.compile(r"\b(is|are|was|were|has|have|had)\b", re.I), r"\1 not"),
)


def propose_negation_flip(text: str) -> tuple[str, str] | None:
    """Return one deterministic polarity flip, never an unrecorded rewrite."""
    for pattern, replacement in _NEGATION_PATTERNS:
        if pattern.search(text):
            mutated = pattern.sub(replacement, text, count=1)
            if mutated != text:
                return mutated, f"regex-negation-flip:{pattern.pattern}"
    return None


@dataclass(frozen=True)
class PilotReviewRow:
    candidate: PresentIrrelevantCandidate
    context_start: int
    context_end: int
    context_text: str
    contradiction_text: str
    contradiction_method: str
    irrelevant_decision: str = "pending"
    irrelevant_reviewer_id: str | None = None
    irrelevant_note: str | None = None
    paraphrase_text: str | None = None
    paraphrase_author_kind: str | None = None
    paraphrase_author_id: str | None = None
    paraphrase_decision: str = "pending"
    paraphrase_reviewer_id: str | None = None
    paraphrase_note: str | None = None
    contradiction_decision: str = "pending"
    contradiction_reviewer_id: str | None = None
    contradiction_note: str | None = None
    input_sha256: str | None = None
    schema: str = REVIEW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REVIEW_SCHEMA:
            raise ValueError(f"unsupported support review schema: {self.schema}")
        if self.context_start < 0 or self.context_end <= self.context_start:
            raise ValueError("support review context offsets must be non-empty")
        if len(self.context_text) != self.context_end - self.context_start:
            raise ValueError("support review context length differs from offsets")
        relative_original = self.candidate.original_start - self.context_start
        relative_distractor = self.candidate.distractor_start - self.context_start
        if self.context_text[
            relative_original : relative_original + len(self.candidate.original_text)
        ] != self.candidate.original_text:
            raise ValueError("support review context does not contain target span")
        if self.context_text[
            relative_distractor : relative_distractor + len(self.candidate.claim_text)
        ] != self.candidate.claim_text:
            raise ValueError("support review context does not contain distractor span")
        if not self.contradiction_text.strip() or not self.contradiction_method.strip():
            raise ValueError("support review requires a recorded contradiction proposal")
        if self.contradiction_text == self.candidate.original_text:
            raise ValueError("contradiction proposal must change the attested claim")
        for label, decision in (
            ("irrelevant", self.irrelevant_decision),
            ("paraphrase", self.paraphrase_decision),
            ("contradiction", self.contradiction_decision),
        ):
            if decision not in DECISIONS:
                raise ValueError(f"unknown {label} review decision: {decision}")
        self._validate_review_fields()
        expected_hash = _sha256_json(self.immutable_payload())
        if self.input_sha256 is not None and self.input_sha256 != expected_hash:
            raise ValueError("support review immutable input hash mismatch")
        object.__setattr__(self, "input_sha256", expected_hash)

    def _validate_review_fields(self) -> None:
        if self.irrelevant_decision == "accepted" and not _reviewer_identity(
            self.irrelevant_reviewer_id
        ):
            raise ValueError("accepted irrelevant ruling requires a reviewer identity")
        paraphrase_fields = (
            self.paraphrase_text,
            self.paraphrase_author_kind,
            self.paraphrase_author_id,
        )
        if self.paraphrase_decision == "accepted":
            if not all(_present(value) for value in paraphrase_fields):
                raise ValueError("accepted paraphrase requires text and author identity")
            if self.paraphrase_author_kind not in AUTHOR_KINDS:
                raise ValueError("accepted paraphrase author must be human or agent")
            if not _reviewer_identity(self.paraphrase_reviewer_id):
                raise ValueError("accepted paraphrase requires a reviewer identity")
        if self.contradiction_decision == "accepted" and not _reviewer_identity(
            self.contradiction_reviewer_id
        ):
            raise ValueError("accepted contradiction requires a reviewer identity")

    @property
    def ready(self) -> bool:
        return (
            self.irrelevant_decision == "accepted"
            and self.paraphrase_decision == "accepted"
            and self.contradiction_decision == "accepted"
        )

    def immutable_payload(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.canonical_payload(),
            "context": {
                "start": self.context_start,
                "end": self.context_end,
                "text": self.context_text,
                "sha256": sha256_text(self.context_text),
            },
            "contradiction_proposal": {
                "text": self.contradiction_text,
                "method": self.contradiction_method,
            },
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "input_sha256": self.input_sha256,
            **self.immutable_payload(),
            "irrelevance_review": {
                "decision": self.irrelevant_decision,
                "reviewer_id": self.irrelevant_reviewer_id,
                "note": self.irrelevant_note,
            },
            "paraphrase": {
                "text": self.paraphrase_text,
                "author": {
                    "kind": self.paraphrase_author_kind,
                    "id": self.paraphrase_author_id,
                },
                "review": {
                    "decision": self.paraphrase_decision,
                    "reviewer_id": self.paraphrase_reviewer_id,
                    "note": self.paraphrase_note,
                },
            },
            "contradiction_review": {
                "decision": self.contradiction_decision,
                "reviewer_id": self.contradiction_reviewer_id,
                "note": self.contradiction_note,
            },
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PilotReviewRow":
        context = _mapping(value, "context")
        proposal = _mapping(value, "contradiction_proposal")
        irrelevant = _mapping(value, "irrelevance_review")
        paraphrase = _mapping(value, "paraphrase")
        author = _mapping(paraphrase, "author")
        paraphrase_review = _mapping(paraphrase, "review")
        contradiction_review = _mapping(value, "contradiction_review")
        if context.get("sha256") != sha256_text(str(context["text"])):
            raise ValueError("support review context hash mismatch")
        return cls(
            schema=str(value.get("schema", REVIEW_SCHEMA)),
            input_sha256=str(value["input_sha256"]),
            candidate=PresentIrrelevantCandidate.from_mapping(
                _mapping(value, "candidate")
            ),
            context_start=int(context["start"]),
            context_end=int(context["end"]),
            context_text=str(context["text"]),
            contradiction_text=str(proposal["text"]),
            contradiction_method=str(proposal["method"]),
            irrelevant_decision=str(irrelevant["decision"]),
            irrelevant_reviewer_id=_optional(irrelevant.get("reviewer_id")),
            irrelevant_note=_optional(irrelevant.get("note")),
            paraphrase_text=_optional(paraphrase.get("text")),
            paraphrase_author_kind=_optional(author.get("kind")),
            paraphrase_author_id=_optional(author.get("id")),
            paraphrase_decision=str(paraphrase_review["decision"]),
            paraphrase_reviewer_id=_optional(paraphrase_review.get("reviewer_id")),
            paraphrase_note=_optional(paraphrase_review.get("note")),
            contradiction_decision=str(contradiction_review["decision"]),
            contradiction_reviewer_id=_optional(
                contradiction_review.get("reviewer_id")
            ),
            contradiction_note=_optional(contradiction_review.get("note")),
        )


@dataclass(frozen=True)
class PilotReviewManifest:
    rows: tuple[PilotReviewRow, ...]
    target_group_count: int
    reserve_count: int
    sampling_seed: int
    max_context_characters: int
    source_pool_sha256: str
    excluded_pool_sha256: str
    lexical_overlap_min: float
    lexical_overlap_max: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        if self.target_group_count <= 0 or self.reserve_count < 0:
            raise ValueError("pilot review target must be positive and reserve non-negative")
        if len(self.rows) != self.target_group_count + self.reserve_count:
            raise ValueError("pilot review row count differs from target plus reserve")
        if len({row.candidate.candidate_id for row in self.rows}) != len(self.rows):
            raise ValueError("pilot review candidate ids must be unique")
        if len({row.candidate.source_id for row in self.rows}) != len(self.rows):
            raise ValueError("pilot review rows must use unique sources")
        if not all(
            _SHA256.fullmatch(value)
            for value in (self.source_pool_sha256, self.excluded_pool_sha256)
        ):
            raise ValueError("pilot review pool identities require lowercase SHA-256")
        if not 0 <= self.lexical_overlap_min < self.lexical_overlap_max <= 1:
            raise ValueError("pilot review lexical overlap bounds are invalid")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": REVIEW_MANIFEST_SCHEMA,
            "target_group_count": self.target_group_count,
            "reserve_count": self.reserve_count,
            "sampling_seed": self.sampling_seed,
            "max_context_characters": self.max_context_characters,
            "source_pool_sha256": self.source_pool_sha256,
            "excluded_pool_sha256": self.excluded_pool_sha256,
            "lexical_overlap_min": self.lexical_overlap_min,
            "lexical_overlap_max": self.lexical_overlap_max,
            "ordered_input_sha256": [row.input_sha256 for row in self.rows],
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], rows: Iterable[PilotReviewRow]
    ) -> "PilotReviewManifest":
        manifest = cls(
            rows=tuple(rows),
            target_group_count=int(value["target_group_count"]),
            reserve_count=int(value["reserve_count"]),
            sampling_seed=int(value["sampling_seed"]),
            max_context_characters=int(value["max_context_characters"]),
            source_pool_sha256=str(value["source_pool_sha256"]),
            excluded_pool_sha256=str(value["excluded_pool_sha256"]),
            lexical_overlap_min=float(value["lexical_overlap_min"]),
            lexical_overlap_max=float(value["lexical_overlap_max"]),
        )
        if value.get("schema") != REVIEW_MANIFEST_SCHEMA:
            raise ValueError("unsupported pilot review manifest schema")
        if value.get("ordered_input_sha256") != [
            row.input_sha256 for row in manifest.rows
        ]:
            raise ValueError("pilot review rows differ from frozen manifest order")
        if value.get("sha256") != manifest.sha256:
            raise ValueError("pilot review manifest self-hash mismatch")
        return manifest


def prepare_review_manifest(
    candidates: Iterable[PresentIrrelevantCandidate],
    sources: Mapping[str, str],
    *,
    target_group_count: int,
    reserve_count: int,
    sampling_seed: int,
    max_context_characters: int,
    source_pool_sha256: str,
    excluded_pool_sha256: str,
    lexical_overlap_min: float,
    lexical_overlap_max: float,
) -> PilotReviewManifest:
    """Freeze a deterministic review order before any semantic ruling exists."""
    ordered = sorted(candidates, key=lambda row: row.candidate_id)
    random.Random(sampling_seed).shuffle(ordered)
    rows = []
    used_sources = set()
    required = target_group_count + reserve_count
    for candidate in ordered:
        if candidate.source_id in used_sources:
            continue
        try:
            source_text = sources[candidate.source_id]
        except KeyError as error:
            raise ValueError(f"missing candidate source: {candidate.source_id}") from error
        proposal = propose_negation_flip(candidate.original_text)
        if proposal is None:
            continue
        try:
            context_start, context_end, context_text = candidate.context_window(
                source_text, max_context_characters
            )
        except ValueError as error:
            if "do not fit" in str(error):
                continue
            raise
        rows.append(
            PilotReviewRow(
                candidate=candidate,
                context_start=context_start,
                context_end=context_end,
                context_text=context_text,
                contradiction_text=proposal[0],
                contradiction_method=proposal[1],
            )
        )
        used_sources.add(candidate.source_id)
        if len(rows) == required:
            return PilotReviewManifest(
                rows=tuple(rows),
                target_group_count=target_group_count,
                reserve_count=reserve_count,
                sampling_seed=sampling_seed,
                max_context_characters=max_context_characters,
                source_pool_sha256=source_pool_sha256,
                excluded_pool_sha256=excluded_pool_sha256,
                lexical_overlap_min=lexical_overlap_min,
                lexical_overlap_max=lexical_overlap_max,
            )
    raise ValueError(f"only {len(rows)} eligible pilot rows for requested {required}")


_DECISION_COLUMNS = (
    "input_sha256",
    "source_id",
    "question",
    "attested_text",
    "present_candidate_text",
    "context_text",
    "irrelevant_decision",
    "irrelevant_reviewer_id",
    "irrelevant_note",
    "paraphrase_text",
    "paraphrase_author_kind",
    "paraphrase_author_id",
    "paraphrase_decision",
    "paraphrase_reviewer_id",
    "paraphrase_note",
    "contradiction_proposal",
    "contradiction_decision",
    "contradiction_reviewer_id",
    "contradiction_note",
)


def review_decisions_tsv(rows: Iterable[PilotReviewRow]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_DECISION_COLUMNS, dialect="excel-tab")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "input_sha256": row.input_sha256,
                "source_id": row.candidate.source_id,
                "question": row.candidate.question,
                "attested_text": row.candidate.original_text,
                "present_candidate_text": row.candidate.claim_text,
                "context_text": row.context_text,
                "irrelevant_decision": row.irrelevant_decision,
                "irrelevant_reviewer_id": row.irrelevant_reviewer_id,
                "irrelevant_note": row.irrelevant_note,
                "paraphrase_text": row.paraphrase_text,
                "paraphrase_author_kind": row.paraphrase_author_kind,
                "paraphrase_author_id": row.paraphrase_author_id,
                "paraphrase_decision": row.paraphrase_decision,
                "paraphrase_reviewer_id": row.paraphrase_reviewer_id,
                "paraphrase_note": row.paraphrase_note,
                "contradiction_proposal": row.contradiction_text,
                "contradiction_decision": row.contradiction_decision,
                "contradiction_reviewer_id": row.contradiction_reviewer_id,
                "contradiction_note": row.contradiction_note,
            }
        )
    return output.getvalue()


def apply_review_decisions_tsv(
    rows: Iterable[PilotReviewRow], text: str
) -> tuple[PilotReviewRow, ...]:
    frozen = tuple(rows)
    by_hash = {row.input_sha256: row for row in frozen}
    reader = csv.DictReader(io.StringIO(text), dialect="excel-tab")
    if reader.fieldnames != list(_DECISION_COLUMNS):
        raise ValueError("pilot review TSV columns differ from frozen template")
    reviewed = {}
    display_fields = {
        "source_id": lambda row: row.candidate.source_id,
        "question": lambda row: row.candidate.question,
        "attested_text": lambda row: row.candidate.original_text,
        "present_candidate_text": lambda row: row.candidate.claim_text,
        "context_text": lambda row: row.context_text,
        "contradiction_proposal": lambda row: row.contradiction_text,
    }
    for number, values in enumerate(reader, 2):
        input_sha256 = values.get("input_sha256", "")
        try:
            row = by_hash[input_sha256]
        except KeyError as error:
            raise ValueError(f"pilot review TSV row {number} has unknown input hash") from error
        if input_sha256 in reviewed:
            raise ValueError(f"pilot review TSV row {number} duplicates input hash")
        for key, getter in display_fields.items():
            if values.get(key) != getter(row):
                raise ValueError(f"pilot review TSV row {number} changed {key}")
        reviewed[input_sha256] = replace(
            row,
            irrelevant_decision=values["irrelevant_decision"],
            irrelevant_reviewer_id=_blank_optional(values["irrelevant_reviewer_id"]),
            irrelevant_note=_blank_optional(values["irrelevant_note"]),
            paraphrase_text=_blank_optional(values["paraphrase_text"]),
            paraphrase_author_kind=_blank_optional(values["paraphrase_author_kind"]),
            paraphrase_author_id=_blank_optional(values["paraphrase_author_id"]),
            paraphrase_decision=values["paraphrase_decision"],
            paraphrase_reviewer_id=_blank_optional(values["paraphrase_reviewer_id"]),
            paraphrase_note=_blank_optional(values["paraphrase_note"]),
            contradiction_decision=values["contradiction_decision"],
            contradiction_reviewer_id=_blank_optional(
                values["contradiction_reviewer_id"]
            ),
            contradiction_note=_blank_optional(values["contradiction_note"]),
        )
    if set(reviewed) != set(by_hash):
        raise ValueError("pilot review TSV does not contain every frozen row")
    return tuple(reviewed[row.input_sha256] for row in frozen)


def _reviewer_identity(value: str | None) -> bool:
    return _present(value)


@dataclass(frozen=True)
class PilotBuildReceipt:
    """What the build walked past to fill the target; makes retries visible."""

    schema: str
    probe_sha256: str
    review_manifest_sha256: str
    build_attempt: int
    contexts_sha256: str
    rows_walked: int
    selected: int
    rejected: int
    ambiguous: int

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


BUILD_RECEIPT_SCHEMA = "groundnut-support-probe-build/v2"


def build_pilot_probe(
    manifest: PilotReviewManifest,
    seeds: Iterable[AttestedSpanSeed],
    sources: Mapping[str, str],
) -> SupportProbe:
    """Promote the first preregistered ready rows; pending rows fail closed."""
    probe, _ = build_pilot_probe_with_receipt(
        manifest, seeds, sources, build_attempt=1
    )
    return probe


def build_pilot_probe_with_receipt(
    manifest: PilotReviewManifest,
    seeds: Iterable[AttestedSpanSeed],
    sources: Mapping[str, str],
    *,
    build_attempt: int,
) -> tuple[SupportProbe, PilotBuildReceipt]:
    """Like build_pilot_probe, and also records rows walked, rejected, ambiguous."""
    if build_attempt < 1:
        raise ValueError("build attempt must be at least 1")
    by_seed = {seed.seed_id: seed for seed in seeds}
    selected = []
    walked = rejected = ambiguous = 0
    for row in manifest.rows:
        walked += 1
        decisions = {
            row.irrelevant_decision,
            row.paraphrase_decision,
            row.contradiction_decision,
        }
        if row.ready:
            selected.append(row)
            if len(selected) == manifest.target_group_count:
                break
        elif "pending" in decisions:
            raise ValueError(
                f"pilot review is pending before target is filled: "
                f"{row.candidate.candidate_id}"
            )
        elif "rejected" in decisions:
            rejected += 1
        else:
            ambiguous += 1
    if len(selected) != manifest.target_group_count:
        raise ValueError(
            f"only {len(selected)} fully accepted groups for target "
            f"{manifest.target_group_count}"
        )
    cases = []
    for row in selected:
        candidate = row.candidate
        try:
            seed = by_seed[candidate.target_seed_id]
            source_text = sources[candidate.source_id]
        except KeyError as error:
            raise ValueError(f"pilot input is missing: {error.args[0]}") from error
        seed.validate_source(source_text)
        candidate.validate_source(source_text)
        if (
            seed.source_id != candidate.source_id
            or seed.source_sha256 != candidate.source_sha256
            or seed.original_start != candidate.original_start
            or seed.original_end != candidate.original_end
            or seed.original_text != candidate.original_text
            or seed.question != candidate.question
        ):
            raise ValueError(f"candidate target differs from seed: {candidate.candidate_id}")
        group_id = f"pilot-{candidate.candidate_id}"
        verbatim = seed.to_verbatim_case(group_id=group_id)
        paraphrase_kind = (
            "authored" if row.paraphrase_author_kind == "human" else "model_authored"
        )
        paraphrase = SupportCase(
            case_id=f"{group_id}-paraphrase_supported",
            group_id=group_id,
            kind="paraphrase_supported",
            expected_status=CASE_KINDS["paraphrase_supported"],
            source_id=seed.source_id,
            source_sha256=seed.source_sha256,
            original_start=seed.original_start,
            original_end=seed.original_end,
            original_text=seed.original_text,
            question=seed.question,
            claim_text=row.paraphrase_text or "",
            present_start=None,
            present_end=None,
            provenance=CaseProvenance(
                kind=paraphrase_kind,
                source="groundnut-pilot-review",
                source_record_id=row.input_sha256 or "",
                method=f"{row.paraphrase_author_kind}:{row.paraphrase_author_id}",
                parent_case_ids=(verbatim.case_id,),
                reviewed_by=(row.paraphrase_reviewer_id or "",),
                note=row.paraphrase_note,
            ),
        )
        if not (
            manifest.lexical_overlap_min
            <= paraphrase.lexical_overlap
            <= manifest.lexical_overlap_max
        ):
            raise ValueError(
                f"paraphrase lexical overlap outside frozen band: {paraphrase.case_id}"
            )
        contradiction = SupportCase(
            case_id=f"{group_id}-contradicted",
            group_id=group_id,
            kind="contradicted",
            expected_status=CASE_KINDS["contradicted"],
            source_id=seed.source_id,
            source_sha256=seed.source_sha256,
            original_start=seed.original_start,
            original_end=seed.original_end,
            original_text=seed.original_text,
            question=seed.question,
            claim_text=row.contradiction_text,
            present_start=None,
            present_end=None,
            provenance=CaseProvenance(
                kind="derived",
                source="groundnut-pilot-review",
                source_record_id=row.input_sha256 or "",
                method=row.contradiction_method,
                parent_case_ids=(verbatim.case_id,),
                reviewed_by=(row.contradiction_reviewer_id or "",),
                note=row.contradiction_note,
            ),
        )
        irrelevant = candidate.to_case(
            group_id=group_id,
            reviewer_id=row.irrelevant_reviewer_id or "",
            review_record_id=row.input_sha256 or "",
        )
        cases.extend((verbatim, paraphrase, contradiction, irrelevant))
    probe = SupportProbe(tuple(cases))
    probe.validate_sources(sources)
    probe.contexts(sources, manifest.max_context_characters)
    receipt = PilotBuildReceipt(
        schema=BUILD_RECEIPT_SCHEMA,
        probe_sha256=probe.sha256,
        review_manifest_sha256=manifest.sha256,
        build_attempt=build_attempt,
        contexts_sha256=contexts_sha256(
            probe.contexts(sources, manifest.max_context_characters)
        ),
        rows_walked=walked,
        selected=len(selected),
        rejected=rejected,
        ambiguous=ambiguous,
    )
    return probe, receipt


def load_review_rows(path: str | Path) -> tuple[PilotReviewRow, ...]:
    rows = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise TypeError("expected object")
            rows.append(PilotReviewRow.from_mapping(value))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}:{number}: invalid pilot review: {error}") from error
    if not rows:
        raise ValueError("pilot review file must contain rows")
    return tuple(rows)


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    row = value.get(key)
    if not isinstance(row, Mapping):
        raise ValueError(f"support review requires object: {key}")
    return row


def _optional(value: Any) -> str | None:
    return None if value is None else str(value)


def _blank_optional(value: str) -> str | None:
    return value if value.strip() else None


def _present(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

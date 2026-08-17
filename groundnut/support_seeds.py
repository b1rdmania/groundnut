"""Contamination-safe evidence seeds for constructing support probes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .provenance import sha256_text
from .support_cases import CaseProvenance, SupportCase


SEED_SCHEMA = "groundnut-support-seed/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AttestedSpanSeed:
    seed_id: str
    source_id: str
    source_sha256: str
    original_start: int
    original_end: int
    original_text: str
    question: str
    provenance: CaseProvenance
    schema: str = SEED_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SEED_SCHEMA:
            raise ValueError(f"unsupported support-seed schema: {self.schema}")
        if self.provenance.kind != "attested":
            raise ValueError("attested span seeds require attested provenance")
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("support-seed source hash must be lowercase SHA-256")
        if not all(value.strip() for value in (self.seed_id, self.source_id, self.original_text, self.question)):
            raise ValueError("support-seed identity and text fields are required")
        if self.original_start < 0 or self.original_end <= self.original_start:
            raise ValueError("support-seed offsets must be non-empty")
        if len(self.original_text) != self.original_end - self.original_start:
            raise ValueError("support-seed text length does not match offsets")

    def validate_source(self, source_text: str) -> None:
        if sha256_text(source_text) != self.source_sha256:
            raise ValueError(f"source hash mismatch for seed {self.seed_id}")
        if source_text[self.original_start : self.original_end] != self.original_text:
            raise ValueError(f"source span mismatch for seed {self.seed_id}")

    def to_verbatim_case(self, *, group_id: str, case_id: str | None = None) -> SupportCase:
        return SupportCase(
            case_id=case_id or f"{group_id}-verbatim_supported",
            group_id=group_id,
            kind="verbatim_supported",
            expected_status="supported",
            source_id=self.source_id,
            source_sha256=self.source_sha256,
            original_start=self.original_start,
            original_end=self.original_end,
            original_text=self.original_text,
            question=self.question,
            claim_text=self.original_text,
            provenance=self.provenance,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "seed_id": self.seed_id,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "original_start": self.original_start,
            "original_end": self.original_end,
            "original_text": self.original_text,
            "question": self.question,
            "provenance": self.provenance.canonical_payload(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AttestedSpanSeed":
        return cls(
            schema=str(value.get("schema", SEED_SCHEMA)),
            seed_id=str(value["seed_id"]),
            source_id=str(value["source_id"]),
            source_sha256=str(value["source_sha256"]),
            original_start=int(value["original_start"]),
            original_end=int(value["original_end"]),
            original_text=str(value["original_text"]),
            question=str(value["question"]),
            provenance=CaseProvenance.from_mapping(value["provenance"]),
        )


@dataclass(frozen=True)
class SeedImport:
    seeds: tuple[AttestedSpanSeed, ...]
    excluded_holdout_sources: tuple[str, ...]
    safe_source_count: int
    source_pool_sha256: str
    excluded_pool_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "excluded_holdout_sources", tuple(sorted(set(self.excluded_holdout_sources))))
        ids = [seed.seed_id for seed in self.seeds]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate support-seed id")
        if self.safe_source_count < 1:
            raise ValueError("support-seed import must contain a safe source")

    def manifest(self) -> dict[str, Any]:
        payload = {
            "schema": "groundnut-support-seed-import/v1",
            "seed_ids": sorted(seed.seed_id for seed in self.seeds),
            "excluded_holdout_sources": list(self.excluded_holdout_sources),
            "safe_source_count": self.safe_source_count,
            "source_pool_sha256": self.source_pool_sha256,
            "excluded_pool_sha256": self.excluded_pool_sha256,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return {**payload, "sha256": hashlib.sha256(encoded).hexdigest()}


def load_support_seeds(path: str | Path) -> tuple[AttestedSpanSeed, ...]:
    seeds = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError("expected object")
            seeds.append(AttestedSpanSeed.from_mapping(value))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}:{number}: invalid support seed: {error}") from error
    ids = [seed.seed_id for seed in seeds]
    if not seeds or len(ids) != len(set(ids)):
        raise ValueError("support-seed file must contain unique seeds")
    return tuple(seeds)


def holdout_hashes_from_manifest(path: str | Path) -> set[str]:
    value = json.loads(Path(path).read_text())
    contracts = value.get("contracts")
    if not isinstance(contracts, dict):
        raise ValueError("Groundnut corpus manifest must contain a contracts object")
    hashes = {
        str(entry["sha256_raw"])
        for entry in contracts.values()
        if isinstance(entry, dict) and entry.get("split") == "holdout"
    }
    if not hashes:
        raise ValueError("Groundnut corpus manifest contains no holdout hashes")
    return hashes


def import_legalbenchrag(
    benchmark_path: str | Path,
    corpus_root: str | Path,
    *,
    groundnut_manifest: str | Path,
    dataset_name: str | None = None,
    expected_safe_sources: int | None = None,
    expected_excluded_sources: int | None = None,
) -> SeedImport:
    """Import LegalBench-RAG snippets while excluding Groundnut holdout bytes.

    The upstream shape is `{tests: [{query, snippets: [{file_path, span}]}]}`.
    Imported spans remain seeds: this function does not manufacture the other
    three semantic cells or promote cross-query pairs to gold.
    """

    benchmark_path = Path(benchmark_path)
    corpus_root = Path(corpus_root).resolve()
    value = json.loads(benchmark_path.read_text())
    tests = value.get("tests")
    if not isinstance(tests, list):
        raise ValueError("LegalBench-RAG benchmark must contain a tests array")
    excluded_hashes = holdout_hashes_from_manifest(groundnut_manifest)
    source_cache: dict[str, tuple[str, str]] = {}
    seeds: list[AttestedSpanSeed] = []
    excluded_sources: list[str] = []
    dataset = dataset_name or benchmark_path.stem

    for test_index, test in enumerate(tests):
        if not isinstance(test, Mapping) or not str(test.get("query", "")).strip():
            raise ValueError(f"LegalBench-RAG test {test_index} has no query")
        snippets = test.get("snippets")
        if not isinstance(snippets, list) or not snippets:
            raise ValueError(f"LegalBench-RAG test {test_index} has no snippets")
        for snippet_index, snippet in enumerate(snippets):
            if not isinstance(snippet, Mapping):
                raise ValueError(f"LegalBench-RAG snippet {test_index}:{snippet_index} is not an object")
            relative = str(snippet.get("file_path", ""))
            source_path = (corpus_root / relative).resolve()
            if corpus_root not in source_path.parents:
                raise ValueError(f"LegalBench-RAG source escapes corpus root: {relative}")
            if relative not in source_cache:
                source_text = source_path.read_text()
                source_cache[relative] = (source_text, sha256_text(source_text))
            source_text, source_sha256 = source_cache[relative]
            if source_sha256 in excluded_hashes:
                excluded_sources.append(relative)
                continue
            span = snippet.get("span")
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                raise ValueError(f"LegalBench-RAG snippet {test_index}:{snippet_index} has invalid span")
            start, end = int(span[0]), int(span[1])
            if start < 0 or end <= start or end > len(source_text):
                raise ValueError(f"LegalBench-RAG snippet {test_index}:{snippet_index} span is out of bounds")
            original = source_text[start:end]
            record_id = f"{benchmark_path.name}:{test_index}:{snippet_index}"
            seed_id = hashlib.sha256(
                f"{dataset}\0{record_id}\0{source_sha256}\0{start}\0{end}".encode()
            ).hexdigest()[:20]
            seeds.append(
                AttestedSpanSeed(
                    seed_id=seed_id,
                    source_id=relative,
                    source_sha256=source_sha256,
                    original_start=start,
                    original_end=end,
                    original_text=original,
                    question=str(test["query"]),
                    provenance=CaseProvenance(
                        kind="attested",
                        source="legalbenchrag",
                        source_record_id=record_id,
                        method="expert span/category; generated category-to-query phrasing",
                        note=f"dataset={dataset}; query wording is not expert-authored",
                    ),
                )
            )

    pool_payload = [
        (relative, digest) for relative, (_, digest) in sorted(source_cache.items()) if digest not in excluded_hashes
    ]
    pool_hash = hashlib.sha256(
        json.dumps(pool_payload, separators=(",", ":")).encode()
    ).hexdigest()
    excluded_pool_hash = hashlib.sha256(
        json.dumps(sorted(excluded_hashes), separators=(",", ":")).encode()
    ).hexdigest()
    safe_source_count = len(pool_payload)
    excluded_source_count = len(set(excluded_sources))
    if expected_safe_sources is not None and safe_source_count != expected_safe_sources:
        raise ValueError(
            "LegalBench-RAG safe source count differs from expected inventory: "
            f"{safe_source_count} != {expected_safe_sources}"
        )
    if expected_excluded_sources is not None and excluded_source_count != expected_excluded_sources:
        raise ValueError(
            "LegalBench-RAG excluded source count differs from expected inventory: "
            f"{excluded_source_count} != {expected_excluded_sources}"
        )
    return SeedImport(
        tuple(seeds),
        tuple(excluded_sources),
        safe_source_count,
        pool_hash,
        excluded_pool_hash,
    )

"""Deterministic navigation cases built from exact source offsets."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
from typing import Any, Mapping, Sequence

from .navigation import NavigationIndex, NavigationNode, node_id_for
from .provenance import sha256_text
from .support_seeds import AttestedSpanSeed, load_support_seeds


NAVIGATION_CASE_SCHEMA = "groundnut-navigation-case/v1"
NAVIGATION_PACK_SCHEMA = "groundnut-navigation-pack/v1"


@dataclass(frozen=True)
class NavigationCase:
    case_id: str
    question: str
    index: NavigationIndex
    gold_node_ids: tuple[str, ...]
    gold_start: int
    gold_end: int
    severity: str = "material"
    provenance: str = "legalbenchrag_attested_span"
    schema: str = NAVIGATION_CASE_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "gold_node_ids", tuple(sorted(self.gold_node_ids)))
        if self.schema != NAVIGATION_CASE_SCHEMA:
            raise ValueError("unsupported navigation case schema")
        if not self.case_id.strip() or not self.question.strip() or not self.gold_node_ids:
            raise ValueError("navigation case identity, question and gold nodes are required")
        if self.gold_start < 0 or self.gold_end <= self.gold_start:
            raise ValueError("navigation case gold offsets are invalid")
        if self.severity not in {"low", "material", "high"}:
            raise ValueError("unknown navigation case severity")
        selectable = {node.node_id for node in self.index.nodes if node.selectable}
        if not set(self.gold_node_ids) <= selectable:
            raise ValueError("navigation case gold nodes must be selectable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "case_id": self.case_id,
            "question": self.question,
            "index": self.index.to_dict(),
            "gold_node_ids": list(self.gold_node_ids),
            "gold_start": self.gold_start,
            "gold_end": self.gold_end,
            "severity": self.severity,
            "provenance": self.provenance,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NavigationCase":
        return cls(
            schema=str(value.get("schema", NAVIGATION_CASE_SCHEMA)),
            case_id=str(value["case_id"]),
            question=str(value["question"]),
            index=NavigationIndex.from_mapping(value["index"]),
            gold_node_ids=tuple(str(row) for row in value["gold_node_ids"]),
            gold_start=int(value["gold_start"]),
            gold_end=int(value["gold_end"]),
            severity=str(value.get("severity", "material")),
            provenance=str(value.get("provenance", "legalbenchrag_attested_span")),
        )


def paragraph_navigation_index(
    source_id: str, source_text: str, *, max_node_characters: int = 3000
) -> NavigationIndex:
    """Build a transparent root/paragraph index without generated summaries."""

    if max_node_characters < 256:
        raise ValueError("max navigation node size must be at least 256 characters")
    source_sha256 = sha256_text(source_text)
    if not source_text.strip():
        raise ValueError("navigation source text must not be empty")
    spans = []
    for match in re.finditer(r"\S[\s\S]*?(?=\n[ \t]*\n|\Z)", source_text):
        start, end = match.span()
        while end > start and source_text[end - 1].isspace():
            end -= 1
        spans.extend(_split_span(source_text, start, end, max_node_characters))
    if not spans:
        raise ValueError("navigation source produced no paragraph nodes")

    root_text_sha256 = sha256_text(source_text)
    root_id = node_id_for(
        source_sha256=source_sha256,
        source_start=0,
        source_end=len(source_text),
        text_sha256=root_text_sha256,
    )
    children = []
    for number, (start, end) in enumerate(spans, 1):
        text = source_text[start:end]
        text_sha256 = sha256_text(text)
        children.append(
            NavigationNode(
                node_id=node_id_for(
                    source_sha256=source_sha256,
                    source_start=start,
                    source_end=end,
                    text_sha256=text_sha256,
                ),
                title=_node_title(text),
                source_start=start,
                source_end=end,
                text_sha256=text_sha256,
                parent_id=root_id,
                native_id=f"paragraph:{number}",
            )
        )
    root = NavigationNode(
        node_id=root_id,
        title=Path(source_id).stem,
        source_start=0,
        source_end=len(source_text),
        text_sha256=root_text_sha256,
        child_ids=tuple(node.node_id for node in children),
        native_id="document-root",
        selectable=False,
    )
    return NavigationIndex(
        source_id=source_id,
        source_sha256=source_sha256,
        indexer_key="groundnut.paragraph-navigation-index",
        indexer_version="1",
        nodes=(root, *children),
    )


def build_navigation_case(
    seed: AttestedSpanSeed,
    source_text: str,
    *,
    max_node_characters: int = 3000,
) -> NavigationCase:
    seed.validate_source(source_text)
    index = paragraph_navigation_index(
        seed.source_id, source_text, max_node_characters=max_node_characters
    )
    gold = tuple(
        node.node_id
        for node in index.nodes
        if node.selectable
        and node.source_start < seed.original_end
        and seed.original_start < node.source_end
    )
    if not gold:
        raise ValueError(f"navigation seed has no overlapping node: {seed.seed_id}")
    return NavigationCase(
        case_id=seed.seed_id,
        question=seed.question,
        index=index,
        gold_node_ids=gold,
        gold_start=seed.original_start,
        gold_end=seed.original_end,
    )


def build_navigation_pack(
    seeds: Sequence[AttestedSpanSeed],
    corpus_root: str | Path,
    *,
    count: int,
    sampling_seed: int,
    unique_sources: bool = True,
    max_node_characters: int = 3000,
) -> dict[str, Any]:
    if count < 1:
        raise ValueError("navigation pack count must be positive")
    corpus_root = Path(corpus_root).resolve()
    ordered = sorted(seeds, key=lambda row: row.seed_id)
    random.Random(sampling_seed).shuffle(ordered)
    selected = []
    seen_sources: set[str] = set()
    for seed in ordered:
        if unique_sources and seed.source_id in seen_sources:
            continue
        source_path = (corpus_root / seed.source_id).resolve()
        if corpus_root not in source_path.parents:
            raise ValueError("navigation source escapes corpus root")
        case = build_navigation_case(
            seed,
            source_path.read_text(),
            max_node_characters=max_node_characters,
        )
        selected.append(case)
        seen_sources.add(seed.source_id)
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f"only {len(selected)} navigation cases were eligible")
    payload = {
        "schema": NAVIGATION_PACK_SCHEMA,
        "sampling_seed": sampling_seed,
        "unique_sources": unique_sources,
        "max_node_characters": max_node_characters,
        "case_count": len(selected),
        "cases": [case.to_dict() for case in sorted(selected, key=lambda row: row.case_id)],
    }
    return {**payload, "sha256": _payload_sha256(payload)}


def build_navigation_pack_from_seed_file(
    seed_path: str | Path, corpus_root: str | Path, **kwargs: Any
) -> dict[str, Any]:
    return build_navigation_pack(load_support_seeds(seed_path), corpus_root, **kwargs)


def load_navigation_pack(path: str | Path) -> tuple[NavigationCase, ...]:
    value = json.loads(Path(path).read_text())
    if value.get("schema") != NAVIGATION_PACK_SCHEMA:
        raise ValueError("unsupported navigation pack schema")
    payload = {key: row for key, row in value.items() if key != "sha256"}
    if value.get("sha256") != _payload_sha256(payload):
        raise ValueError("navigation pack self-hash mismatch")
    cases = tuple(NavigationCase.from_mapping(row) for row in value["cases"])
    if len(cases) != value.get("case_count") or len({row.case_id for row in cases}) != len(cases):
        raise ValueError("navigation pack case inventory is invalid")
    return cases


def _split_span(
    source_text: str, start: int, end: int, max_characters: int
) -> list[tuple[int, int]]:
    rows = []
    cursor = start
    while end - cursor > max_characters:
        limit = cursor + max_characters
        boundary = source_text.rfind(" ", cursor + max_characters // 2, limit)
        if boundary <= cursor:
            boundary = limit
        rows.append((cursor, boundary))
        cursor = boundary
        while cursor < end and source_text[cursor].isspace():
            cursor += 1
    if cursor < end:
        rows.append((cursor, end))
    return rows


def _node_title(text: str) -> str:
    title = " ".join(text.split())[:180].strip()
    return title or "Untitled source segment"


def _payload_sha256(value: Any) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

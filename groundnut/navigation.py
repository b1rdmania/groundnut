"""Hash-bound structured navigation contracts.

Navigation chooses candidate evidence. It does not answer a question, assess
support, or establish truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .provenance import sha256_text


NAVIGATION_INDEX_SCHEMA = "groundnut-navigation-index/v1"
NAVIGATION_SELECTION_SCHEMA = "groundnut-navigation-selection/v1"
NAVIGATION_RECEIPT_SCHEMA = "groundnut-navigation-receipt/v1"
NAVIGATOR_IDENTITY_SCHEMA = "groundnut-navigator-identity/v1"
SELECTION_STATUSES = {"selected", "abstained", "failed"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class NavigationNode:
    node_id: str
    title: str
    source_start: int
    source_end: int
    text_sha256: str
    parent_id: str | None = None
    child_ids: tuple[str, ...] = ()
    native_id: str | None = None
    summary: str | None = None
    summary_provenance: str = "none"
    selectable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_ids", tuple(self.child_ids))
        if not self.node_id.strip() or not self.title.strip():
            raise ValueError("navigation node identity and title are required")
        if self.source_start < 0 or self.source_end <= self.source_start:
            raise ValueError("navigation node source offsets are invalid")
        if not _SHA256.fullmatch(self.text_sha256):
            raise ValueError("navigation node text hash must be lowercase SHA-256")
        if self.parent_id is not None and not self.parent_id.strip():
            raise ValueError("navigation node parent id must not be empty")
        if len(self.child_ids) != len(set(self.child_ids)):
            raise ValueError("navigation node child ids must be unique")
        if self.node_id in self.child_ids:
            raise ValueError("navigation node cannot be its own child")
        if self.native_id is not None and not self.native_id.strip():
            raise ValueError("navigation node native id must not be empty")
        if self.summary is not None and not self.summary.strip():
            raise ValueError("navigation node summary must not be empty")
        if self.summary_provenance not in {"none", "native", "derived", "authored"}:
            raise ValueError("unknown navigation summary provenance")
        if self.summary is None and self.summary_provenance != "none":
            raise ValueError("summary provenance requires a summary")
        if self.summary is not None and self.summary_provenance == "none":
            raise ValueError("navigation summary requires explicit provenance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "text_sha256": self.text_sha256,
            "parent_id": self.parent_id,
            "child_ids": list(self.child_ids),
            "native_id": self.native_id,
            "summary": self.summary,
            "summary_provenance": self.summary_provenance,
            "selectable": self.selectable,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NavigationNode":
        return cls(
            node_id=str(value["node_id"]),
            title=str(value["title"]),
            source_start=int(value["source_start"]),
            source_end=int(value["source_end"]),
            text_sha256=str(value["text_sha256"]),
            parent_id=(str(value["parent_id"]) if value.get("parent_id") else None),
            child_ids=tuple(str(row) for row in value.get("child_ids", ())),
            native_id=(str(value["native_id"]) if value.get("native_id") else None),
            summary=(str(value["summary"]) if value.get("summary") else None),
            summary_provenance=str(value.get("summary_provenance", "none")),
            selectable=bool(value.get("selectable", True)),
        )


@dataclass(frozen=True)
class NavigationIndex:
    source_id: str
    source_sha256: str
    indexer_key: str
    indexer_version: str
    nodes: tuple[NavigationNode, ...]
    schema: str = NAVIGATION_INDEX_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(sorted(self.nodes, key=lambda n: n.node_id)))
        if self.schema != NAVIGATION_INDEX_SCHEMA:
            raise ValueError(f"unsupported navigation index schema: {self.schema}")
        if not (
            self.source_id.strip()
            and self.indexer_key.strip()
            and self.indexer_version.strip()
        ):
            raise ValueError("navigation index identity is required")
        if not _SHA256.fullmatch(self.source_sha256) or not self.nodes:
            raise ValueError("navigation index requires a source hash and nodes")
        by_id = {node.node_id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("navigation node ids must be unique")
        roots = [node for node in self.nodes if node.parent_id is None]
        if not roots:
            raise ValueError("navigation index requires at least one root")
        root_end = max(row.source_end for row in roots)
        for node in self.nodes:
            if node.source_end > root_end:
                raise ValueError("navigation node escapes root source envelope")
            if node.parent_id is not None:
                parent = by_id.get(node.parent_id)
                if parent is None or node.node_id not in parent.child_ids:
                    raise ValueError("navigation parent/child relationship is inconsistent")
                if not (
                    parent.source_start <= node.source_start
                    and node.source_end <= parent.source_end
                ):
                    raise ValueError("navigation node escapes parent source envelope")
            for child_id in node.child_ids:
                child = by_id.get(child_id)
                if child is None or child.parent_id != node.node_id:
                    raise ValueError("navigation child/parent relationship is inconsistent")
        _reject_cycles(by_id)

    @property
    def by_id(self) -> dict[str, NavigationNode]:
        return {node.node_id: node for node in self.nodes}

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "indexer": {"key": self.indexer_key, "version": self.indexer_version},
            "nodes": [node.to_dict() for node in self.nodes],
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NavigationIndex":
        indexer = value.get("indexer")
        if not isinstance(indexer, Mapping):
            raise ValueError("navigation index indexer must be an object")
        result = cls(
            schema=str(value.get("schema", NAVIGATION_INDEX_SCHEMA)),
            source_id=str(value["source_id"]),
            source_sha256=str(value["source_sha256"]),
            indexer_key=str(indexer["key"]),
            indexer_version=str(indexer["version"]),
            nodes=tuple(NavigationNode.from_mapping(row) for row in value["nodes"]),
        )
        if value.get("sha256") is not None and value["sha256"] != result.sha256:
            raise ValueError("navigation index self-hash mismatch")
        return result


@dataclass(frozen=True)
class NavigatorIdentity:
    adapter: str
    revision: str
    package: str
    package_version: str
    code_spdx: str
    code_source: str
    configuration: Mapping[str, Any] = field(default_factory=dict)
    schema: str = NAVIGATOR_IDENTITY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != NAVIGATOR_IDENTITY_SCHEMA:
            raise ValueError("unsupported navigator identity schema")
        if not all(
            value.strip()
            for value in (
                self.adapter,
                self.revision,
                self.package,
                self.package_version,
                self.code_spdx,
                self.code_source,
            )
        ):
            raise ValueError("navigator identity fields are required")
        _canonical_json(self.configuration)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "adapter": self.adapter,
            "revision": self.revision,
            "package": self.package,
            "package_version": self.package_version,
            "code_spdx": self.code_spdx,
            "code_source": self.code_source,
            "configuration": dict(self.configuration),
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


@dataclass(frozen=True)
class NavigationSelection:
    status: str
    selected_node_ids: tuple[str, ...]
    reason: str
    question_sha256: str
    index_sha256: str
    navigator: NavigatorIdentity
    raw_output: Any
    prompt_sha256: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    schema: str = NAVIGATION_SELECTION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_node_ids", tuple(self.selected_node_ids))
        if self.schema != NAVIGATION_SELECTION_SCHEMA or self.status not in SELECTION_STATUSES:
            raise ValueError("invalid navigation selection schema or status")
        if not (
            self.reason.strip()
            and _SHA256.fullmatch(self.question_sha256)
            and _SHA256.fullmatch(self.index_sha256)
        ):
            raise ValueError("navigation selection reason and input hashes are required")
        if len(self.selected_node_ids) != len(set(self.selected_node_ids)):
            raise ValueError("navigation selection node ids must be unique")
        if self.status == "selected" and not self.selected_node_ids:
            raise ValueError("selected navigation result requires node ids")
        if self.status != "selected" and self.selected_node_ids:
            raise ValueError("non-selected navigation result cannot carry node ids")
        if self.prompt_sha256 is not None and not _SHA256.fullmatch(self.prompt_sha256):
            raise ValueError("navigation prompt hash must be lowercase SHA-256")
        if any(
            value is not None and value < 0
            for value in (self.input_tokens, self.output_tokens)
        ):
            raise ValueError("navigation token counts cannot be negative")
        _canonical_json(self.raw_output)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "selected_node_ids": list(self.selected_node_ids),
            "reason": self.reason,
            "question_sha256": self.question_sha256,
            "index_sha256": self.index_sha256,
            "navigator": self.navigator.to_dict(),
            "raw_output": self.raw_output,
            "raw_output_sha256": _sha256(self.raw_output),
            "prompt_sha256": self.prompt_sha256,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


@dataclass(frozen=True)
class NavigationReceipt:
    selection: NavigationSelection
    selected_nodes: tuple[Mapping[str, Any], ...]
    context_sha256: str
    context_characters: int
    schema: str = NAVIGATION_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_nodes", tuple(self.selected_nodes))
        if self.schema != NAVIGATION_RECEIPT_SCHEMA or self.selection.status != "selected":
            raise ValueError("navigation receipt requires a selected result")
        if not _SHA256.fullmatch(self.context_sha256) or self.context_characters < 1:
            raise ValueError("navigation receipt context identity is invalid")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "selection": self.selection.to_dict(),
            "selected_nodes": [dict(row) for row in self.selected_nodes],
            "context_sha256": self.context_sha256,
            "context_characters": self.context_characters,
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def fetch_selected_nodes(
    index: NavigationIndex, selection: NavigationSelection, source_text: str
) -> tuple[str, NavigationReceipt]:
    """Fetch exact selected node text after validating every identity."""

    if selection.status != "selected" or selection.index_sha256 != index.sha256:
        raise ValueError("navigation selection is not fetchable for this index")
    if sha256_text(source_text) != index.source_sha256:
        raise ValueError("navigation source hash mismatch")
    by_id = index.by_id
    records = []
    parts = []
    for node_id in selection.selected_node_ids:
        node = by_id.get(node_id)
        if node is None or not node.selectable:
            raise ValueError(f"navigation selected invalid node: {node_id}")
        text = source_text[node.source_start : node.source_end]
        if sha256_text(text) != node.text_sha256:
            raise ValueError(f"navigation node text hash mismatch: {node_id}")
        parts.append(text)
        records.append(
            {
                "node_id": node.node_id,
                "native_id": node.native_id,
                "source_start": node.source_start,
                "source_end": node.source_end,
                "text_sha256": node.text_sha256,
            }
        )
    context = "\n\n".join(parts)
    return context, NavigationReceipt(
        selection=selection,
        selected_nodes=tuple(records),
        context_sha256=sha256_text(context),
        context_characters=len(context),
    )


def node_id_for(
    *, source_sha256: str, source_start: int, source_end: int, text_sha256: str
) -> str:
    return _sha256(
        {
            "source_sha256": source_sha256,
            "source_start": source_start,
            "source_end": source_end,
            "text_sha256": text_sha256,
        }
    )[:24]


def question_sha256(question: str) -> str:
    if not question.strip():
        raise ValueError("navigation question must not be empty")
    return sha256_text(question)


def _reject_cycles(by_id: Mapping[str, NavigationNode]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("navigation index contains a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child_id in by_id[node_id].child_ids:
            visit(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in by_id:
        visit(node_id)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as error:
        raise ValueError("navigation value must be finite JSON") from error


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()

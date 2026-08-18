"""Structured-navigation adapters with strict TreeDex-style node selection."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping, Protocol

from ..navigation import (
    NavigationIndex,
    NavigationSelection,
    NavigatorIdentity,
    question_sha256,
)
from ..provenance import sha256_text


_TOKEN = re.compile(r"[a-z0-9]+")
TREE_SURFACE_SCHEMA = "groundnut-compact-navigation-tree/v1"
HANDLE_TREE_SURFACE_SCHEMA = "groundnut-compact-navigation-handle-tree/v1"
SELECTABLE_HANDLE_TREE_SURFACE_SCHEMA = (
    "groundnut-compact-navigation-selectable-handle-tree/v1"
)
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "between", "by", "consider",
    "contract", "does", "for", "from", "in", "is", "it", "of", "on", "or",
    "the", "this", "to", "what", "when", "where", "which", "who", "with",
}


class TreeSelector(Protocol):
    def __call__(self, prompt: str) -> Mapping[str, Any]: ...


class FullInjectionNavigator:
    """Selection baseline that exposes every selectable source node."""

    identity = NavigatorIdentity(
        adapter="groundnut.navigation.full-injection",
        revision="1",
        package="groundnut",
        package_version="1",
        code_spdx="Apache-2.0",
        code_source="https://github.com/b1rdmania/groundnut",
        configuration={"selection": "all selectable nodes in source order"},
    )

    def select(self, index: NavigationIndex, question: str) -> NavigationSelection:
        node_ids = tuple(
            node.node_id
            for node in sorted(index.nodes, key=lambda row: row.source_start)
            if node.selectable
        )
        return NavigationSelection(
            status="selected",
            selected_node_ids=node_ids,
            reason="Full-injection baseline selected every source node.",
            question_sha256=question_sha256(question),
            index_sha256=index.sha256,
            navigator=self.identity,
            raw_output={"selected_node_ids": list(node_ids)},
        )


class LexicalStructureNavigator:
    """Transparent title/summary token-overlap navigation floor."""

    def __init__(self, *, max_nodes: int = 3) -> None:
        if max_nodes < 1:
            raise ValueError("lexical navigator max_nodes must be positive")
        self.max_nodes = max_nodes
        self.identity = NavigatorIdentity(
            adapter="groundnut.navigation.lexical-structure",
            revision="1",
            package="groundnut",
            package_version="1",
            code_spdx="Apache-2.0",
            code_source="https://github.com/b1rdmania/groundnut",
            configuration={
                "max_nodes": max_nodes,
                "tokenizer": "lowercase-alphanumeric",
                "stop_words": sorted(_STOP),
                "score": "query-token recall over title plus summary",
            },
        )

    def select(self, index: NavigationIndex, question: str) -> NavigationSelection:
        query = _tokens(question)
        scores = []
        for node in index.nodes:
            if not node.selectable:
                continue
            surface = _tokens(f"{node.title} {node.summary or ''}")
            shared = query & surface
            score = len(shared) / len(query) if query else 0.0
            scores.append((score, node.source_start, node.node_id, sorted(shared)))
        eligible = [row for row in scores if row[0] > 0]
        eligible.sort(key=lambda row: (-row[0], row[1], row[2]))
        chosen = eligible[: self.max_nodes]
        raw = {
            "scores": [
                {"node_id": node_id, "score": score, "shared_tokens": shared}
                for score, _, node_id, shared in sorted(scores, key=lambda row: row[1])
            ],
            "max_nodes": self.max_nodes,
        }
        if not chosen:
            return NavigationSelection(
                status="abstained",
                selected_node_ids=(),
                reason="No query tokens overlap the navigation surface.",
                question_sha256=question_sha256(question),
                index_sha256=index.sha256,
                navigator=self.identity,
                raw_output=raw,
            )
        node_ids = tuple(row[2] for row in sorted(chosen, key=lambda row: row[1]))
        return NavigationSelection(
            status="selected",
            selected_node_ids=node_ids,
            reason="Selected the highest query-token-recall navigation nodes.",
            question_sha256=question_sha256(question),
            index_sha256=index.sha256,
            navigator=self.identity,
            raw_output=raw,
        )


class TreeDexStyleNavigator:
    """One-shot compact-tree selection with Groundnut fail-closed semantics.

    The selection shape follows TreeDex's useful core. Groundnut deliberately
    rejects TreeDex-style automatic first-node fallbacks and answer generation.
    """

    def __init__(
        self,
        selector: TreeSelector,
        *,
        model: str,
        revision: str,
        package_version: str,
        max_nodes: int = 5,
        max_prompt_characters: int | None = None,
        max_output_tokens: int | None = None,
        input_token_counter: Callable[[str], int] | None = None,
        runtime_configuration: Mapping[str, Any] | None = None,
        selector_id_mode: str = "node_id",
    ) -> None:
        if max_nodes < 1:
            raise ValueError("tree navigator max_nodes must be positive")
        self.selector = selector
        self.max_nodes = max_nodes
        if max_prompt_characters is not None and max_prompt_characters < 1:
            raise ValueError("tree navigator prompt budget must be positive")
        self.max_prompt_characters = max_prompt_characters
        if max_output_tokens is not None and max_output_tokens < 1:
            raise ValueError("tree navigator output budget must be positive")
        self.max_output_tokens = max_output_tokens
        self.input_token_counter = input_token_counter
        if selector_id_mode not in {
            "node_id",
            "short_handle",
            "selectable_short_handle",
        }:
            raise ValueError("unknown tree navigator selector identity mode")
        self.selector_id_mode = selector_id_mode
        uses_handles = selector_id_mode != "node_id"
        selectable_handles_only = selector_id_mode == "selectable_short_handle"
        adapter = (
            "groundnut.navigation.treedex-selectable-handle"
            if selectable_handles_only
            else (
                "groundnut.navigation.treedex-short-handle"
                if uses_handles
                else "groundnut.navigation.treedex-style"
            )
        )
        adapter_revision = "1" if uses_handles else "3"
        surface_schema = (
            SELECTABLE_HANDLE_TREE_SURFACE_SCHEMA
            if selectable_handles_only
            else (HANDLE_TREE_SURFACE_SCHEMA if uses_handles else TREE_SURFACE_SCHEMA)
        )
        prompt_template = (
            _SELECTABLE_HANDLE_PROMPT
            if selectable_handles_only
            else (_HANDLE_PROMPT if uses_handles else _TREEDEX_PROMPT)
        )
        configuration = {
            "model": model,
            "model_revision": revision,
            "max_nodes": max_nodes,
            "max_prompt_characters": max_prompt_characters,
            "max_output_tokens": max_output_tokens,
            "selection": (
                "one-shot compact tree with deterministic short handles"
                if uses_handles
                else "one-shot compact tree"
            ),
            "tree_surface_schema": surface_schema,
            "prompt_template_sha256": sha256_text(prompt_template),
            "unknown_ids": "fail",
            "empty_selection": "abstain",
            "answer_generation": False,
            "mechanism_donor": "alisawuffles/treedex",
            "mechanism_donor_revision": (
                "cb506162ef9e14eac41ba032d3a21879aa2c8770e"
            ),
            "mechanism_donor_spdx": "MIT",
            "runtime": dict(runtime_configuration or {}),
        }
        if uses_handles:
            configuration.update(
                {
                    "selector_id_mode": selector_id_mode,
                    "selector_handle_scheme": (
                        "selectable-source-order nNNNN; receipt resolves to content node id"
                        if selectable_handles_only
                        else "source-order nNNNN; receipt resolves to content node id"
                    ),
                }
            )
        self.identity = NavigatorIdentity(
            adapter=adapter,
            revision=adapter_revision,
            package=model,
            package_version=package_version,
            code_spdx="Apache-2.0",
            code_source="https://github.com/b1rdmania/groundnut",
            configuration=configuration,
        )

    def select(self, index: NavigationIndex, question: str) -> NavigationSelection:
        uses_handles = self.selector_id_mode != "node_id"
        selectable_handles_only = (
            self.selector_id_mode == "selectable_short_handle"
        )
        node_id_by_handle = _short_handle_map(
            index, selectable_only=selectable_handles_only
        )
        handle_by_node_id = {value: key for key, value in node_id_by_handle.items()}
        surface = _tree_surface(
            index,
            handle_by_node_id=handle_by_node_id if uses_handles else None,
            selectable_handles_only=selectable_handles_only,
        )
        prompt_template = (
            _SELECTABLE_HANDLE_PROMPT
            if selectable_handles_only
            else (_HANDLE_PROMPT if uses_handles else _TREEDEX_PROMPT)
        )
        prompt = prompt_template.format(
            question=question,
            max_nodes=self.max_nodes,
            tree=json.dumps(surface, sort_keys=True, separators=(",", ":")),
        )
        base = {
            "question_sha256": question_sha256(question),
            "index_sha256": index.sha256,
            "navigator": self.identity,
            "prompt_sha256": sha256_text(prompt),
        }
        counted_input_tokens = (
            self.input_token_counter(prompt) if self.input_token_counter else None
        )
        if self.max_prompt_characters is not None and len(prompt) > self.max_prompt_characters:
            return NavigationSelection(
                status="abstained",
                selected_node_ids=(),
                reason="Structured index exceeds the frozen navigation prompt budget.",
                raw_output={
                    "prompt_characters": len(prompt),
                    "max_prompt_characters": self.max_prompt_characters,
                },
                input_tokens=counted_input_tokens,
                **base,
            )
        try:
            raw = dict(self.selector(prompt))
        except Exception as error:
            return NavigationSelection(
                status="failed",
                selected_node_ids=(),
                reason=f"Tree selector failed: {type(error).__name__}",
                raw_output={"error_type": type(error).__name__},
                **base,
            )
        selector_field = "node_handles" if uses_handles else "node_ids"
        ids = raw.get(selector_field)
        input_tokens = (
            int(raw["input_tokens"])
            if isinstance(raw.get("input_tokens"), int)
            else counted_input_tokens
        )
        output_tokens = (
            int(raw["output_tokens"])
            if isinstance(raw.get("output_tokens"), int)
            else None
        )
        if (
            self.max_output_tokens is not None
            and output_tokens is not None
            and output_tokens > self.max_output_tokens
        ):
            return NavigationSelection(
                status="failed",
                selected_node_ids=(),
                reason="Tree selector exceeded the frozen output-token budget.",
                raw_output=raw,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                **base,
            )
        if not isinstance(ids, list) or any(not isinstance(row, str) for row in ids):
            return NavigationSelection(
                status="failed",
                selected_node_ids=(),
                reason=f"Tree selector returned an invalid {selector_field} field.",
                raw_output=raw,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                **base,
            )
        if len(ids) != len(set(ids)) or len(ids) > self.max_nodes:
            return NavigationSelection(
                status="failed",
                selected_node_ids=(),
                reason="Tree selector violated node-count or uniqueness constraints.",
                raw_output=raw,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                **base,
            )
        if not ids:
            return NavigationSelection(
                status="abstained",
                selected_node_ids=(),
                reason="Tree selector returned no evidence nodes.",
                raw_output=raw,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                **base,
            )
        by_id = index.by_id
        if uses_handles:
            invalid_handles = [handle for handle in ids if handle not in node_id_by_handle]
            if invalid_handles:
                return NavigationSelection(
                    status="failed",
                    selected_node_ids=(),
                    reason="Tree selector returned unknown short handles.",
                    raw_output={**raw, "invalid_node_handles": invalid_handles},
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    **base,
                )
            ids = [node_id_by_handle[handle] for handle in ids]
        invalid = [
            node_id
            for node_id in ids
            if node_id not in by_id or not by_id[node_id].selectable
        ]
        if invalid:
            return NavigationSelection(
                status="failed",
                selected_node_ids=(),
                reason="Tree selector returned unknown or non-selectable node ids.",
                raw_output={**raw, "invalid_node_ids": invalid},
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                **base,
            )
        ordered = tuple(sorted(ids, key=lambda node_id: by_id[node_id].source_start))
        resolved_raw = (
            {**raw, "resolved_node_ids": list(ordered)} if uses_handles else raw
        )
        return NavigationSelection(
            status="selected",
            selected_node_ids=ordered,
            reason="Tree selector returned a valid bounded node set.",
            raw_output=resolved_raw,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            **base,
        )


class TreeHandleNavigator(TreeDexStyleNavigator):
    """TreeDex-style selector using short handles resolved to content IDs."""

    def __init__(self, selector: TreeSelector, **kwargs: Any) -> None:
        super().__init__(selector, selector_id_mode="short_handle", **kwargs)


class SelectableTreeHandleNavigator(TreeDexStyleNavigator):
    """Short-handle selector that never assigns handles to structural nodes."""

    def __init__(self, selector: TreeSelector, **kwargs: Any) -> None:
        super().__init__(
            selector, selector_id_mode="selectable_short_handle", **kwargs
        )


def _tree_surface(
    index: NavigationIndex,
    *,
    handle_by_node_id: Mapping[str, str] | None = None,
    selectable_handles_only: bool = False,
) -> dict[str, Any]:
    by_id = index.by_id

    def row(node_id: str) -> list[Any]:
        node = by_id[node_id]
        return [
            (
                handle_by_node_id.get(node.node_id)
                if handle_by_node_id
                else node.node_id
            ),
            node.title,
            node.native_id,
            node.summary,
            node.summary_provenance,
            node.selectable,
            [row(child_id) for child_id in node.child_ids],
        ]

    roots = sorted(
        (node for node in index.nodes if node.parent_id is None),
        key=lambda node: node.source_start,
    )
    return {
        "schema": (
            SELECTABLE_HANDLE_TREE_SURFACE_SCHEMA
            if selectable_handles_only
            else (HANDLE_TREE_SURFACE_SCHEMA if handle_by_node_id else TREE_SURFACE_SCHEMA)
        ),
        "legend": [
            "selector_handle" if handle_by_node_id else "node_id",
            "title",
            "native_id",
            "summary",
            "summary_provenance",
            "selectable",
            "children",
        ],
        "roots": [row(root.node_id) for root in roots],
    }


def _short_handle_map(
    index: NavigationIndex, *, selectable_only: bool = False
) -> dict[str, str]:
    ordered = sorted(index.nodes, key=lambda node: (node.source_start, node.node_id))
    if selectable_only:
        ordered = [node for node in ordered if node.selectable]
    width = max(4, len(str(len(ordered))))
    return {
        f"n{position:0{width}d}": node.node_id
        for position, node in enumerate(ordered, 1)
    }


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN.findall(value.casefold()) if token not in _STOP}


_TREEDEX_PROMPT = """You are a document navigation system, not an answer generator.
Select at most {max_nodes} nodes from the structured index that are likely to
contain evidence needed to answer the question. Return only a JSON object with
`node_ids`. Return an empty node_ids list when the index does not contain
suitable evidence. Never invent a node id. Do not return an answer or rationale.

Question: {question}

Structured index:
{tree}
"""

_HANDLE_PROMPT = """You are a document navigation system, not an answer generator.
Select at most {max_nodes} nodes from the structured index that are likely to
contain evidence needed to answer the question. Return only a JSON object with
`node_handles`. Return an empty node_handles list when the index does not
contain suitable evidence. Copy handles exactly from the index. Do not return
an answer, rationale, content hash, native id, or title.

Question: {question}

Structured index:
{tree}
"""

_SELECTABLE_HANDLE_PROMPT = """You are a document navigation system, not an answer generator.
Select at most {max_nodes} evidence nodes from the structured index that are
likely to answer the question. Return only a JSON object with `node_handles`.
Only non-null selector_handle values are selectable. Rows with a null handle
are structural containers and must never be returned. Return an empty
node_handles list when no suitable evidence exists. Copy handles exactly. Do
not return an answer, rationale, content hash, native id, or title.

Question: {question}

Structured index:
{tree}
"""

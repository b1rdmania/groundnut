"""Offline JSON boundary for lossless source passages, not evidence qualification.

Reuses navigation identities without invoking a navigator or admitting semantic support.
"""

from __future__ import annotations

import json
import re
import sys

from .navigation import NavigationIndex, NavigationNode, node_id_for
from .provenance import sha256_text

REQUEST_SCHEMA = "groundnut-passage-request/v1"
RESPONSE_SCHEMA = "groundnut-passage-register/v1"


def passage_index(source_id: str, text: str, max_characters: int) -> NavigationIndex:
    """Index every character exactly once, splitting at whitespace where possible."""
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be nonempty text")
    if not isinstance(text, str) or not text:
        raise ValueError("source text must be nonempty")
    if type(max_characters) is not int or max_characters < 1:
        raise ValueError("max_characters must be a positive integer")
    source_hash = sha256_text(text)
    nodes = []
    start = 0
    while start < len(text):
        end = min(start + max_characters, len(text))
        if end < len(text):
            breaks = list(re.finditer(r"\s+", text[start:end]))
            if breaks:
                end = start + breaks[-1].end()
        text_hash = sha256_text(text[start:end])
        nodes.append(
            NavigationNode(
                node_id=node_id_for(
                    source_sha256=source_hash,
                    source_start=start,
                    source_end=end,
                    text_sha256=text_hash,
                ),
                title=f"Characters {start}:{end}",
                source_start=start,
                source_end=end,
                text_sha256=text_hash,
            )
        )
        start = end
    return NavigationIndex(
        source_id=source_id,
        source_sha256=source_hash,
        indexer_key="lossless_passages",
        indexer_version="1",
        nodes=tuple(nodes),
    )


def execute_request(request: dict) -> dict:
    if not isinstance(request, dict) or request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("unsupported passage request schema")
    sources = request.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a nonempty array")
    seen = set()
    passages = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("source must be an object")
        sid, text = source.get("source_id"), source.get("text")
        index = passage_index(sid, text, request.get("max_characters", 1600))
        if sid in seen:
            raise ValueError("duplicate source_id")
        seen.add(sid)
        for node in sorted(index.nodes, key=lambda n: n.source_start):
            passages.append(
                {
                    "passage_id": f"{sid}:{node.node_id}",
                    "source_id": sid,
                    "source_sha256": index.source_sha256,
                    "text_sha256": node.text_sha256,
                    "start": node.source_start,
                    "end": node.source_end,
                    "exact_text": text[node.source_start : node.source_end],
                }
            )
    return {"schema": RESPONSE_SCHEMA, "passages": passages}


def main() -> int:
    try:
        response = execute_request(json.load(sys.stdin))
    except (ValueError, TypeError, KeyError) as error:
        print(json.dumps({"schema": "groundnut-passage-error/v1", "error": str(error)}))
        return 2
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

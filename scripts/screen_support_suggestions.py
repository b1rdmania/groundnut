#!/usr/bin/env python3
"""Create a non-admissible development screen from agent suggestions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_agent_screen import (  # noqa: E402
    AgentSuggestion,
    screen_agent_suggestions,
)
from groundnut.support_review import PilotReviewManifest, PilotReviewRow  # noqa: E402


def json_object(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-jsonl", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--suggestions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = tuple(
        PilotReviewRow.from_mapping(json.loads(line))
        for line in args.review_jsonl.read_text().splitlines()
        if line.strip()
    )
    manifest = PilotReviewManifest.from_mapping(json_object(args.manifest), rows)
    suggestions = tuple(
        AgentSuggestion.from_mapping(json.loads(line))
        for line in args.suggestions.read_text().splitlines()
        if line.strip()
    )
    screen = screen_agent_suggestions(manifest, suggestions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(screen.to_dict(), indent=2) + "\n")
    print(
        f"wrote {args.output}: {len(screen.included_input_sha256)} included, "
        f"{len(screen.excluded)} excluded; admission=false"
    )


if __name__ == "__main__":
    main()

"""Render a frozen support-pilot review batch as a private offline HTML app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_review import PilotReviewManifest, load_review_rows  # noqa: E402
from groundnut.support_review_html import render_support_review_html  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the support review worksheet as self-contained HTML."
    )
    parser.add_argument("--review-jsonl", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--suggestions", type=Path, help="agent suggestion JSONL")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        rows = load_review_rows(args.review_jsonl)
        manifest = PilotReviewManifest.from_mapping(
            json.loads(args.manifest.read_text()), rows
        )
        suggestions = {}
        if args.suggestions:
            for number, line in enumerate(args.suggestions.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                suggestion = json.loads(line)
                if suggestion.get("schema") != "groundnut-support-agent-suggestion/v1":
                    raise ValueError(f"suggestions line {number}: unsupported schema")
                input_sha256 = str(suggestion["input_sha256"])
                if input_sha256 in suggestions:
                    raise ValueError(f"suggestions line {number}: duplicate input hash")
                suggestions[input_sha256] = suggestion
        unknown = set(suggestions) - {row.input_sha256 for row in rows}
        if unknown:
            raise ValueError("suggestions reference rows outside the frozen batch")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_support_review_html(manifest, suggestions))
    print(f"WROTE PRIVATE OFFLINE REVIEWER: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

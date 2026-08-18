#!/usr/bin/env python3
"""Rebuild a navigation receipt from frozen raw selector outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.adapters.navigation import (  # noqa: E402
    TreeDexStyleNavigator,
    TreeHandleNavigator,
    SelectableTreeHandleNavigator,
)
from groundnut.navigation_cases import load_navigation_pack  # noqa: E402
from groundnut.navigation_eval import (  # noqa: E402
    run_navigation_evaluation,
    validate_navigation_evaluation,
)
from groundnut.provenance import sha256_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recorded-result", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    recorded = json.loads(args.recorded_result.read_text())
    validate_navigation_evaluation(recorded)
    if len(recorded.get("summaries", ())) != 1:
        raise ValueError("recorded replay input must contain exactly one navigator")
    old_identity = recorded["summaries"][0]["navigator"]
    configuration = old_identity["configuration"]
    selection_by_prompt = {
        row["selection"]["prompt_sha256"]: row["selection"]
        for row in recorded["rows"]
        if row["selection"].get("prompt_sha256")
        and row["selection"]["reason"]
        != "Structured index exceeds the frozen navigation prompt budget."
    }

    def replay(prompt: str) -> dict:
        prompt_hash = sha256_text(prompt)
        if prompt_hash not in selection_by_prompt:
            raise ValueError("recorded result has no output for navigation prompt")
        selection = selection_by_prompt[prompt_hash]
        if selection["reason"].startswith("Tree selector failed: "):
            raise RecordedSelectorError(str(selection["raw_output"]["error_type"]))
        return dict(selection["raw_output"])

    navigator_class = {
        None: TreeDexStyleNavigator,
        "short_handle": TreeHandleNavigator,
        "selectable_short_handle": SelectableTreeHandleNavigator,
    }[configuration.get("selector_id_mode")]
    navigator = navigator_class(
        replay,
        model=configuration["model"],
        revision=configuration["model_revision"],
        package_version=old_identity["package_version"],
        max_nodes=int(configuration["max_nodes"]),
        max_prompt_characters=_optional_int(configuration["max_prompt_characters"]),
        max_output_tokens=_optional_int(configuration["max_output_tokens"]),
        runtime_configuration=configuration["runtime"],
    )
    result = run_navigation_evaluation(
        load_navigation_pack(args.pack), args.corpus_root, (navigator,)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "sha256": result["sha256"]}, indent=2))
    return 0


class RecordedSelectorError(Exception):
    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.recorded_error_type = error_type


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


if __name__ == "__main__":
    raise SystemExit(main())

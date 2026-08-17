"""Create a fail-closed Groundnut render receipt from two local artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from .artifacts import ArtifactProfile, DEFAULT_ARTIFACT_PROFILE
from .rendering import RendererIdentity, compare_rendered_artifacts


def _json_object(path: str | None, label: str) -> Mapping[str, Any]:
    if path is None:
        return {}
    value = json.loads(Path(path).read_text())
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _profile(path: str | None) -> ArtifactProfile:
    return (
        ArtifactProfile.from_mapping(_json_object(path, "artifact profile"))
        if path
        else DEFAULT_ARTIFACT_PROFILE
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--rendered", required=True)
    parser.add_argument("--renderer-name", required=True)
    parser.add_argument("--renderer-version", required=True)
    parser.add_argument("--renderer-config", help="renderer configuration JSON")
    parser.add_argument("--source-profile", help="source artifact profile JSON")
    parser.add_argument("--rendered-profile", help="rendered artifact profile JSON")
    parser.add_argument("--out", help="receipt JSON; omit to write stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        receipt = compare_rendered_artifacts(
            args.source,
            args.rendered,
            renderer=RendererIdentity(
                args.renderer_name,
                args.renderer_version,
                _json_object(args.renderer_config, "renderer configuration"),
            ),
            source_profile=_profile(args.source_profile),
            rendered_profile=_profile(args.rendered_profile),
        ).to_dict()
        encoded = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        if args.out:
            Path(args.out).write_text(encoded)
        else:
            sys.stdout.write(encoded)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"render receipt error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

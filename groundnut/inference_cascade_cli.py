"""Standalone CLI for the non-admissible inference-cascade experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .inference_cascade import (
    InferenceCascadeManifest,
    analyze_inference_cascades,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an advisory inference-cascade challenge map."
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        manifest_value = json.loads(args.manifest.read_text())
        if not isinstance(manifest_value, dict):
            raise ValueError("cascade manifest must be a JSON object")
        manifest = InferenceCascadeManifest.from_mapping(manifest_value)
        report_sha256 = hashlib.sha256(args.report.read_bytes()).hexdigest()
        if report_sha256 != manifest.report_sha256:
            raise ValueError("cascade manifest does not match the report bytes")
        receipt = analyze_inference_cascades(manifest)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"INVALID: {error}")
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        "CASCADE EXPERIMENT: "
        f"{receipt['root_challenge_count']} roots, "
        f"{receipt['impacted_node_count']} downstream nodes; advisory only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

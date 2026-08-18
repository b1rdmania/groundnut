#!/usr/bin/env python3
"""Compare Groundnut fixed windows with pinned semchunk on safe dev documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.segmentation_experiment import (  # noqa: E402
    Segment,
    SegmenterSpec,
    compare_segmenters,
)


SEMCHUNK_REVISION = "dccb2f7fc2248e6266d6cbb1c0d986a3f192c3fe"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=REPO / "eval/dev/contracts")
    parser.add_argument("--predictions", type=Path, default=REPO / "predictions/dev")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    _reject_holdout(args.corpus)
    documents = {
        path.stem: path.read_text()
        for path in sorted(args.corpus.glob("*.txt"))
    }
    predictions = _load_predictions(args.predictions)

    try:
        import semchunk
        from importlib.metadata import version
    except ImportError as exc:
        raise SystemExit("Install the pinned experiment dependency: semchunk==4.1.1") from exc
    if version("semchunk") != "4.1.1":
        raise SystemExit("E2 is pinned to semchunk==4.1.1")

    chunker = semchunk.chunkerify(len, 20_000)

    def segment(text: str):
        chunks, offsets = chunker(text, offsets=True, overlap=500)
        return tuple(
            Segment(start, end, chunk)
            for chunk, (start, end) in zip(chunks, offsets, strict=True)
        )

    result = compare_segmenters(
        documents,
        predictions,
        baseline_spec=SegmenterSpec(
            key="groundnut.fixed-character-windows",
            version="1",
            revision=hashlib.sha256((REPO / "pipeline/chunking.py").read_bytes()).hexdigest(),
            licence_spdx="Apache-2.0",
            max_characters=20_000,
            overlap_characters=500,
        ),
        candidate_spec=SegmenterSpec(
            key="isaacus-dev/semchunk",
            version="4.1.1",
            revision=SEMCHUNK_REVISION,
            licence_spdx="MIT",
            max_characters=20_000,
            overlap_characters=500,
        ),
        candidate_segmenter=segment,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), **result["summary"], "sha256": result["sha256"]}, indent=2))
    return 0


def _load_predictions(root: Path) -> dict[str, tuple[str, ...]]:
    rows = {}
    for path in sorted(root.glob("*.json")):
        value = json.loads(path.read_text())
        findings = value.get("findings", value)
        rows[path.stem] = tuple(
            span
            for spans in findings.values()
            if isinstance(spans, list)
            for span in spans
            if isinstance(span, str) and span
        )
    return rows


def _reject_holdout(path: Path) -> None:
    if "holdout" in {part.lower() for part in path.resolve().parts}:
        raise SystemExit("E2 must not read the protected holdout")


if __name__ == "__main__":
    raise SystemExit(main())

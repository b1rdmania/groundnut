"""Import contamination-safe LegalBench-RAG spans as Groundnut seeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_seeds import import_legalbenchrag  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import LegalBench-RAG snippets without Groundnut holdout overlap."
    )
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO / "eval" / "CORPUS-MANIFEST.json",
    )
    parser.add_argument("--dataset-name")
    parser.add_argument("--expected-safe-sources", type=int)
    parser.add_argument("--expected-excluded-sources", type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = import_legalbenchrag(
        args.benchmark,
        args.corpus_root,
        groundnut_manifest=args.manifest,
        dataset_name=args.dataset_name,
        expected_safe_sources=args.expected_safe_sources,
        expected_excluded_sources=args.expected_excluded_sources,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(seed.canonical_payload(), sort_keys=True) + "\n"
            for seed in sorted(result.seeds, key=lambda item: item.seed_id)
        )
    )
    manifest_path = args.output.with_name(f"{args.output.name}.manifest.json")
    manifest_path.write_text(json.dumps(result.manifest(), indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "seeds": len(result.seeds),
                "safe_sources": result.safe_source_count,
                "excluded_holdout_sources": len(result.excluded_holdout_sources),
                "source_pool_sha256": result.source_pool_sha256,
                "excluded_pool_sha256": result.excluded_pool_sha256,
                "output": str(args.output),
                "manifest": str(manifest_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

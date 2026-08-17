"""Freeze a contamination-safe support-pilot review batch and TSV worksheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_review import (  # noqa: E402
    prepare_review_manifest,
    review_decisions_tsv,
)
from groundnut.support_seeds import (  # noqa: E402
    build_present_irrelevant_candidates,
    load_support_seeds,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the frozen human-review boundary for a support pilot."
    )
    parser.add_argument("--seeds", required=True, type=Path)
    parser.add_argument("--seed-manifest", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--target-groups", type=int, default=50)
    parser.add_argument("--reserve-groups", type=int, default=25)
    parser.add_argument("--sampling-seed", type=int, default=991)
    parser.add_argument("--max-context-characters", type=int, default=4096)
    parser.add_argument("--lexical-overlap-min", type=float, default=0.2)
    parser.add_argument("--lexical-overlap-max", type=float, default=0.8)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    seeds = load_support_seeds(args.seeds)
    source_ids = {seed.source_id for seed in seeds}
    sources = _load_sources(args.corpus_root, source_ids)
    seed_manifest = _load_self_hashed_json(args.seed_manifest)
    manifest = prepare_review_manifest(
        build_present_irrelevant_candidates(seeds),
        sources,
        target_group_count=args.target_groups,
        reserve_count=args.reserve_groups,
        sampling_seed=args.sampling_seed,
        max_context_characters=args.max_context_characters,
        source_pool_sha256=str(seed_manifest["source_pool_sha256"]),
        excluded_pool_sha256=str(seed_manifest["excluded_pool_sha256"]),
        lexical_overlap_min=args.lexical_overlap_min,
        lexical_overlap_max=args.lexical_overlap_max,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(row.canonical_payload(), sort_keys=True) + "\n"
            for row in manifest.rows
        )
    )
    manifest_path = args.output.with_name(f"{args.output.name}.manifest.json")
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")
    tsv_path = args.output.with_suffix(".tsv")
    tsv_path.write_text(review_decisions_tsv(manifest.rows))
    print(
        json.dumps(
            {
                "schema": manifest.to_dict()["schema"],
                "target_groups": manifest.target_group_count,
                "reserve_groups": manifest.reserve_count,
                "review_rows": len(manifest.rows),
                "sha256": manifest.sha256,
                "review_jsonl": str(args.output),
                "manifest": str(manifest_path),
                "worksheet": str(tsv_path),
            },
            sort_keys=True,
        )
    )
    return 0


def _load_sources(corpus_root: Path, source_ids: set[str]) -> dict[str, str]:
    root = corpus_root.resolve()
    sources = {}
    for source_id in sorted(source_ids):
        path = (root / source_id).resolve()
        if root not in path.parents:
            raise ValueError(f"source escapes corpus root: {source_id}")
        sources[source_id] = path.read_text()
    return sources


def _load_self_hashed_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("seed manifest must be an object")
    supplied = value.get("sha256")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if supplied != actual:
        raise ValueError("seed manifest self-hash mismatch")
    return value


if __name__ == "__main__":
    raise SystemExit(main())

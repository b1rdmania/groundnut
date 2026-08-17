"""Freeze the support-probe protocol after review and before learned runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.probe_plan import SupportProbePlan  # noqa: E402
from groundnut.support import SupportPolicy  # noqa: E402
from groundnut.support_cases import SupportProbe  # noqa: E402
from groundnut.support_review import (  # noqa: E402
    PilotReviewManifest,
    load_review_rows,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze a reviewed support probe and exact policy identities."
    )
    parser.add_argument("--key", required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--review-jsonl", required=True, type=Path)
    parser.add_argument("--review-manifest", required=True, type=Path)
    parser.add_argument("--baseline-policy", action="append", required=True, type=Path)
    parser.add_argument("--detector-policy", action="append", required=True, type=Path)
    parser.add_argument("--primary-metric", default="macro_f1")
    parser.add_argument("--minimum-improvement", type=float, required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        rows = load_review_rows(args.review_jsonl)
        review = PilotReviewManifest.from_mapping(
            json.loads(args.review_manifest.read_text()), rows
        )
        probe = SupportProbe.from_jsonl(args.probe)
        if probe.group_count != review.target_group_count:
            raise ValueError("probe group count differs from frozen review target")
        baseline = tuple(SupportPolicy.from_json(path) for path in args.baseline_policy)
        detectors = tuple(SupportPolicy.from_json(path) for path in args.detector_policy)
        policies = baseline + detectors
        plan = SupportProbePlan(
            key=args.key,
            frozen_at=args.frozen_at,
            group_count=probe.group_count,
            sampling_seed=review.sampling_seed,
            probe_sha256=probe.sha256,
            source_pool_sha256=review.source_pool_sha256,
            excluded_pool_sha256=review.excluded_pool_sha256,
            max_context_characters=review.max_context_characters,
            primary_metric=args.primary_metric,
            minimum_improvement=args.minimum_improvement,
            baseline_policy_keys=tuple(policy.key for policy in baseline),
            detector_policy_keys=tuple(policy.key for policy in detectors),
            policy_hashes={policy.key: policy.sha256 for policy in policies},
            lexical_overlap_min=review.lexical_overlap_min,
            lexical_overlap_max=review.lexical_overlap_max,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n")
    print(json.dumps(plan.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

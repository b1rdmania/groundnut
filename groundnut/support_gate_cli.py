"""Offline CLI for the canonical semantic-support admission gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .probe_plan import SupportProbePlan
from .support_admission import RecordedProbeRun, evaluate_support_admission


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a frozen support detector run.")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        report = evaluate_support_admission(
            SupportProbePlan.from_json(args.plan),
            RecordedProbeRun.from_json(args.baseline),
            RecordedProbeRun.from_json(args.candidate),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
    print(
        f"SUPPORT GATE: {'PASS' if report.passed else 'FAIL'} — "
        f"{report.primary_metric} {report.baseline_value:.4f} -> "
        f"{report.candidate_value:.4f} ({report.improvement:+.4f})"
    )
    for failure in report.failures:
        print(f"  {failure}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

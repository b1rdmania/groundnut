"""Build the three-bucket claim ledger for a report from its canonical run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifacts import ArtifactProfile, DEFAULT_ARTIFACT_PROFILE
from .ledger import build_claim_ledger, render_ledger_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, help="canonical response or execution JSON")
    parser.add_argument("--artifact", required=True, type=Path, help="the markdown report the run checked")
    parser.add_argument("--profile", type=Path, help="artifact profile JSON used for the run")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--title", default="Claim ledger")
    args = parser.parse_args(argv)

    try:
        profile = (
            ArtifactProfile.from_mapping(json.loads(args.profile.read_text()))
            if args.profile
            else DEFAULT_ARTIFACT_PROFILE
        )
        ledger = build_claim_ledger(
            json.loads(args.run.read_text()), args.artifact.read_text(), profile=profile
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ledger.to_dict(), indent=2, sort_keys=True) + "\n")
    if args.markdown:
        args.markdown.write_text(render_ledger_markdown(ledger, title=args.title))
    counts = ledger.counts
    population = ledger.population.to_dict(units=len(ledger.rows))
    print(
        json.dumps(
            {
                "units": counts["units"],
                **counts["by_bucket"],
                "population_status": population["status"],
                "annotation_conflicts": counts["annotation_conflicts"],
                "sha256": ledger.sha256,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

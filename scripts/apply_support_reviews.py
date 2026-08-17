"""Apply human TSV decisions to an immutable support-pilot review batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_review import (  # noqa: E402
    PilotReviewManifest,
    apply_review_decisions_tsv,
    load_review_rows,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and apply a completed support-pilot TSV worksheet."
    )
    parser.add_argument("--review-jsonl", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--worksheet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        rows = load_review_rows(args.review_jsonl)
        manifest_value = json.loads(args.manifest.read_text())
        PilotReviewManifest.from_mapping(manifest_value, rows)
        reviewed = apply_review_decisions_tsv(rows, args.worksheet.read_text())
        PilotReviewManifest.from_mapping(manifest_value, reviewed)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(row.canonical_payload(), sort_keys=True) + "\n"
            for row in reviewed
        )
    )
    print(
        json.dumps(
            {
                "rows": len(reviewed),
                "ready": sum(row.ready for row in reviewed),
                "pending": sum(
                    "pending"
                    in {
                        row.irrelevant_decision,
                        row.paraphrase_decision,
                        row.contradiction_decision,
                    }
                    for row in reviewed
                ),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

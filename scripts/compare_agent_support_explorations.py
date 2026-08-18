#!/usr/bin/env python3
"""Compare self-hashed non-admissible support exploration runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from groundnut.support_exploration import compare_agent_explorations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True, metavar="KEY=PATH",
        help="named exploration run; supply at least twice",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = {}
    for item in args.run:
        key, separator, path = item.partition("=")
        if not separator or not key or key in runs:
            parser.error(f"invalid or duplicate --run: {item}")
        runs[key] = json.loads(Path(path).read_text())
    result = compare_agent_explorations(runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

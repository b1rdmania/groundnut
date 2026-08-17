#!/bin/bash
# Usage: harness/gate.sh [dev|dev-full|holdout] [--pred-root DIR]
# Runs all four gate criteria (F1, grounding, High-sev precision, probe gap);
# exits non-zero if any bar fails. Holdout mode consumes the 6h holdout stamp.
cd "$(dirname "$0")/.." && exec python3 harness/gate.py "$@"

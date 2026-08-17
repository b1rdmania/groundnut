#!/bin/bash
# Usage: harness/score.sh [dev|dev-full|holdout|probe]   (default: dev = fixed 80-doc working set)
cd "$(dirname "$0")/.." && exec python3 harness/score.py "${1:-dev}"

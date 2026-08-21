#!/bin/bash
# Wall-clock, score history, and token burn. The loop's self-awareness gauge.
cd "$(dirname "$0")/.."
START_FILE="runs/started-at"
[ -f "$START_FILE" ] || date +%s > "$START_FILE"
start=$(cat "$START_FILE"); now=$(date +%s)
h=$(( (now - start) / 3600 )); m=$(( ((now - start) % 3600) / 60 ))
echo "elapsed: ${h}h ${m}m (budget in docs/history/goal.md: 12h)"
echo "--- score history (last 10) ---"
[ -f runs/history.csv ] && tail -10 runs/history.csv || echo "(no scores yet)"
echo "--- token burn (runs/usage.jsonl) ---"
if [ -f runs/usage.jsonl ]; then
  python3 - <<'EOF'
import json
tin = tout = calls = 0
by_backend = {}
for line in open("runs/usage.jsonl"):
    try: u = json.loads(line)
    except Exception: continue
    calls += 1
    tin += u.get("in_tokens", 0); tout += u.get("out_tokens", 0)
    b = u.get("backend", "?")
    by_backend[b] = by_backend.get(b, 0) + u.get("in_tokens", 0) + u.get("out_tokens", 0)
print(f"calls: {calls}  in: {tin:,}  out: {tout:,}")
for b, t in by_backend.items():
    print(f"  {b}: {t:,} tokens")
if calls:
    print(f"NOTE: agent-backend tokens draw on the Claude subscription quota. Watch gain per token: if the last two cycles moved macro-F1 < 0.005 while burning > 1M tokens, change strategy or stop.")
EOF
else
  echo "(no usage logged yet)"
fi

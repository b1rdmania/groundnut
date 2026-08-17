"""Judges 2 and 3 of the four-criteria eval gate (see gate.py). Deterministic
only — no LLM anywhere on the pass/fail path.

Judge 2 — QUOTE GROUNDING: fraction of predicted spans that appear verbatim in
the source contract. Tolerance is fixed and deterministic: unicode quotes/
dashes/nbsp folded to ASCII, whitespace runs collapsed to single spaces,
case-folded, then plain substring test. Bar >= 0.95.

Judge 3 — HIGH-SEVERITY PRECISION: micro precision restricted to predictions
in High-severity categories (severity >= HIGH_SEVERITY_MIN in
harness/severity.json). Severity derives from category — the same derivation
the dealroom extractor uses to rank its report — so a prediction and a gold
finding in the same category carry the same severity by construction. A High
prediction is a TP iff it matches a gold span of that category under
score.py's Jaccard matcher (the one matching rule; nothing re-invented here).
Bar >= 0.70.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import match  # noqa: E402  — reuse the F1 judge's matcher

REPO = Path(__file__).resolve().parent.parent
HIGH_SEVERITY_MIN = 4
MISS_REPORT_CAP = 10

_WS = re.compile(r"\s+")
_TRANS = str.maketrans({
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',   # curly double quotes
    "–": "-", "—": "-",   # en/em dash
    " ": " ",                   # non-breaking space
})


def norm_text(s):
    return _WS.sub(" ", s.translate(_TRANS)).strip().lower()


def load_severity():
    sev = json.loads((REPO / "harness" / "severity.json").read_text())
    return {k: v for k, v in sev.items() if not k.startswith("_")}


def _load_findings(pred_file):
    try:
        f = json.loads(pred_file.read_text()).get("findings", {})
    except Exception:
        return {}
    return f if isinstance(f, dict) else {}


def grounding(pred_dir, contracts_dir, doc_ids=None):
    """Judge 2. Returns (grounded, total, misses) where misses is a capped
    list of (doc_id, category, span_head) for ungrounded spans."""
    pred_dir, contracts_dir = Path(pred_dir), Path(contracts_dir)
    grounded = total = 0
    misses = []
    for pf in sorted(pred_dir.glob("*.json")):
        doc_id = pf.stem
        if doc_ids is not None and doc_id not in doc_ids:
            continue
        src = contracts_dir / f"{doc_id}.txt"
        if not src.exists():
            continue
        source = norm_text(src.read_text(errors="replace"))
        for cat, spans in _load_findings(pf).items():
            if not isinstance(spans, list):
                continue
            for s in spans:
                if not isinstance(s, str) or not s.strip():
                    continue
                total += 1
                if norm_text(s) in source:
                    grounded += 1
                elif len(misses) < MISS_REPORT_CAP:
                    misses.append((doc_id, cat, " ".join(s.split())[:80]))
    return grounded, total, misses


def high_severity_precision(pred_dir, gold, sevmap=None):
    """Judge 3. Returns (tp, fp) over predictions in High-severity categories,
    scored against the same gold dict shape score.py uses."""
    sevmap = sevmap or load_severity()
    high = {c for c, s in sevmap.items() if s >= HIGH_SEVERITY_MIN}
    pred_dir = Path(pred_dir)
    tp = fp = 0
    for doc_id, entry in gold.items():
        preds = _load_findings(pred_dir / f"{doc_id}.json")
        for cat in high:
            gspans = entry["gold"].get(cat, [])
            pspans = preds.get(cat, []) or []
            if not isinstance(pspans, list):
                continue
            for p in pspans:
                if not isinstance(p, str) or not p.strip():
                    continue
                if match(p, gspans):
                    tp += 1
                else:
                    fp += 1
    return tp, fp

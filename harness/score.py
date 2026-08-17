"""Scorer for groundnut. Called via score.sh — not directly by the optimizer.

Reads gold answers from ~/.dd-eval-private/ (outside the repo). Runs the lint
first; ANY violation voids the score and reports nothing else (details go to
the private lint report, for the human only).
"""
import json, re, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRIV = Path.home() / ".dd-eval-private"
JACCARD_T = 0.5
FN_REPORT_CAP = 20
HOLDOUT_MIN_INTERVAL_S = 6 * 3600

WORD = re.compile(r"[a-z0-9]+")

def norm_tokens(s):
    return set(WORD.findall(s.lower()))

def match(pred, golds):
    pt = norm_tokens(pred)
    if not pt:
        return False
    for g in golds:
        gt = norm_tokens(g)
        if not gt:
            continue
        j = len(pt & gt) / len(pt | gt)
        if j >= JACCARD_T:
            return True
    return False

# ---------------- lint ----------------

def lint(gold_all):
    """Capacity caps + eval-literal overlap. Returns list of violations."""
    viol = []
    gold_texts = set()
    for split in gold_all.values():
        for doc in split.values():
            for spans in doc["gold"].values():
                for s in spans:
                    t = " ".join(s.lower().split())
                    if len(t) >= 25:
                        gold_texts.add(t)
    pipe = REPO / "pipeline"
    str_lit = re.compile(r"\"([^\"\n]{12,})\"|'([^'\n]{12,})'")
    total_lits = 0
    dataset_ref = re.compile(r"cuad|atticus|maud|zenodo", re.I)
    for f in sorted(pipe.rglob("*")):
        if f.is_dir() or f.suffix in {".pyc"} or "__pycache__" in f.parts:
            continue
        try:
            src = f.read_text()
        except Exception:
            continue
        if dataset_ref.search(src):
            viol.append(f"dataset-ref: {f.relative_to(REPO)} references the eval's public source")
        lits = [a or b for a, b in str_lit.findall(src)]
        total_lits += len(lits)
        # capacity caps: per-file and global bank of long string literals
        if len(lits) > 40:
            viol.append(f"capacity: {f.relative_to(REPO)} has {len(lits)} long string literals (cap 40)")
        if total_lits > 300:
            viol.append(f"capacity: pipeline/ exceeds 300 long string literals in total")
            break
        for lit in lits:
            t = " ".join(lit.lower().split())
            if len(t) >= 25:
                for g in gold_texts:
                    if t in g or g in t:
                        viol.append(f"eval-literal: {f.relative_to(REPO)}")
                        break
                else:
                    continue
                break
    return viol

# ---------------- scoring ----------------

def score_split(pred_dir, gold, cats):
    per_cat = {c: [0, 0, 0] for c in cats}  # TP, FP, FN
    fns = []
    for doc_id, entry in gold.items():
        pf = pred_dir / f"{doc_id}.json"
        preds = {}
        if pf.exists():
            try:
                preds = json.loads(pf.read_text()).get("findings", {})
            except Exception:
                pass
        for cat in cats:
            gspans = entry["gold"].get(cat, [])
            pspans = preds.get(cat, []) or []
            if not isinstance(pspans, list):
                pspans = []
            matched_gold = 0
            for g in gspans:
                if any(match(p, [g]) for p in pspans):
                    matched_gold += 1
            tp = sum(1 for p in pspans if match(p, gspans))
            fp = len(pspans) - tp
            fn = len(gspans) - matched_gold
            per_cat[cat][0] += tp
            per_cat[cat][1] += max(fp, 0)
            per_cat[cat][2] += max(fn, 0)
            if fn > 0 and len(fns) < FN_REPORT_CAP:
                fns.append((doc_id, cat))
    return per_cat, fns

def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f

def macro_f1(per_cat):
    fs = [prf(*v)[2] for v in per_cat.values() if sum(v) > 0]
    return sum(fs) / len(fs) if fs else 0.0

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dev"
    cats = json.loads((REPO / "eval" / "categories.json").read_text())
    gold_all = {}
    for split in ("dev", "holdout"):
        p = PRIV / f"{split}-answers.json"
        gold_all[split] = json.loads(p.read_text()) if p.exists() else {}
    probe_p = PRIV / "probe-answers.json"

    viol = lint(gold_all)
    if viol:
        report = PRIV / "lint-report.log"
        with report.open("a") as fh:
            fh.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ({mode})\n")
            for v in viol:
                fh.write(v + "\n")
        print("VOID: constraint violation")
        sys.exit(3)

    if mode == "holdout":
        stamp = PRIV / "holdout-calls.log"
        now = time.time()
        if stamp.exists():
            lines = stamp.read_text().strip().splitlines()
            if lines and now - float(lines[-1].split(",")[0]) < HOLDOUT_MIN_INTERVAL_S:
                print("DENIED: holdout rate limit (1 per 6h)")
                sys.exit(4)
        per_cat, _ = score_split(REPO / "predictions" / "holdout", gold_all["holdout"], cats)
        mf = macro_f1(per_cat)
        with stamp.open("a") as fh:
            fh.write(f"{now},{mf:.4f}\n")
        print(f"holdout macro-F1: {mf:.4f}")
        return

    if mode == "probe":
        if not probe_p.exists():
            print("no probe answers; run harness/probe.sh first")
            sys.exit(2)
        gold_probe = json.loads(probe_p.read_text())
        per_cat, _ = score_split(REPO / "predictions" / "probe", gold_probe, cats)
        mf = macro_f1(per_cat)
        # dev score restricted to the same docs, for a fair gap
        sample_ids = set(gold_probe.keys())
        dev_sub = {k.split("-probe")[0]: v for k, v in gold_probe.items()}
        per_cat_dev, _ = score_split(REPO / "predictions" / "dev",
                                     {d: gold_all["dev"][d] for d in dev_sub if d in gold_all["dev"]}, cats)
        mfd = macro_f1(per_cat_dev)
        print(f"dev(sample) macro-F1: {mfd:.4f}  probe macro-F1: {mf:.4f}  GAP: {mfd - mf:+.4f}")
        return

    # dev (default: fixed stratified working set) / dev-full (all 306)
    gold_dev = gold_all["dev"]
    if mode != "dev-full":
        ws = set(json.loads((REPO / "eval" / "dev" / "working-set.json").read_text()))
        gold_dev = {d: e for d, e in gold_dev.items() if d in ws}
    per_cat, fns = score_split(REPO / "predictions" / "dev", gold_dev, cats)
    mf = macro_f1(per_cat)
    tp = sum(v[0] for v in per_cat.values()); fp = sum(v[1] for v in per_cat.values()); fn = sum(v[2] for v in per_cat.values())
    p, r, f = prf(tp, fp, fn)
    print(f"{mode} ({len(gold_dev)} docs) macro-F1: {mf:.4f}   micro P/R/F1: {p:.3f}/{r:.3f}/{f:.3f}")
    print("per-category (P/R/F1):")
    for c in cats:
        cp, cr, cf = prf(*per_cat[c])
        if sum(per_cat[c]):
            print(f"  {c}: {cp:.2f}/{cr:.2f}/{cf:.2f}")
    if fns:
        print(f"first {len(fns)} false-negative (doc, category) pairs — no gold text is ever shown:")
        for d, c in fns:
            print(f"  {d}  {c}")
    hist = REPO / "runs" / "history.csv"
    hist.parent.mkdir(exist_ok=True)
    with hist.open("a") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')},{mode},{mf:.4f}\n")

if __name__ == "__main__":
    main()

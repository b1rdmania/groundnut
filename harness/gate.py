"""Four-criteria eval gate for groundnut (shape doc §4). One run, one table,
one exit code. All judges deterministic — no LLM on the pass/fail path.

  1. macro-F1            >= 0.55   (harness/score.py — judge 1)
  2. quote-grounding     >= 0.95   (harness/judges.py — judge 2)
  3. High-sev precision  >= 0.70   (harness/judges.py — judge 3)
  4. probe gap           <= +0.05  (dev-sample vs probe macro-F1 — judge 4;
                                    one-sided: a negative gap is safe noise)

Usage:
  python3 harness/gate.py [dev|dev-full|holdout] [--pred-root DIR]

--pred-root points at an alternative predictions tree (containing dev/ and
optionally probe/), e.g. runs/predictions-deepseek-v3, for retro-scoring
cached model outputs. Default: predictions/.

Exit codes: 0 = all four bars pass · 1 = any bar failed or not measurable ·
3 = lint VOID (same rule as score.py) · 4 = holdout rate-limited.
Holdout mode shares score.py's one-per-6h stamp (~/.dd-eval-private/
holdout-calls.log) — a gate run on holdout counts as the holdout spend.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (  # noqa: E402
    REPO, PRIV, HOLDOUT_MIN_INTERVAL_S, lint, score_split, macro_f1, prf,
)
from judges import grounding, high_severity_precision, load_severity  # noqa: E402

BAR_F1 = 0.55
BAR_GROUNDING = 0.95
BAR_HIGH_PRECISION = 0.70
BAR_PROBE_GAP = 0.05  # one-sided upper bound


def evaluate_bars(
    *, macro_f1_value, grounded, grounding_total, high_tp, high_fp, probe_gap
):
    """Evaluate the frozen bars, including non-vacuity requirements."""

    grounding_value = grounded / grounding_total if grounding_total else 0.0
    high_precision = high_tp / (high_tp + high_fp) if high_tp + high_fp else 0.0
    return [
        (
            "macro-F1",
            f"{macro_f1_value:.4f}",
            f">= {BAR_F1}",
            macro_f1_value >= BAR_F1,
        ),
        (
            "quote-grounding",
            f"{grounding_value:.4f} ({grounded}/{grounding_total})",
            f">= {BAR_GROUNDING}",
            grounding_total > 0 and grounding_value >= BAR_GROUNDING,
        ),
        (
            "High-sev precision",
            f"{high_precision:.4f} ({high_tp}/{high_tp + high_fp})",
            f">= {BAR_HIGH_PRECISION}",
            (high_tp + high_fp) > 0 and high_precision >= BAR_HIGH_PRECISION,
        ),
        (
            "probe gap",
            "not measured" if probe_gap is None else f"{probe_gap:+.4f}",
            f"<= +{BAR_PROBE_GAP}",
            probe_gap is not None and probe_gap <= BAR_PROBE_GAP,
        ),
    ]


def main():
    args = [a for a in sys.argv[1:]]
    pred_root = REPO / "predictions"
    if "--pred-root" in args:
        i = args.index("--pred-root")
        pred_root = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    mode = args[0] if args else "dev"
    if mode not in ("dev", "dev-full", "holdout"):
        print(f"unknown mode: {mode}")
        sys.exit(2)

    cats = json.loads((REPO / "eval" / "categories.json").read_text())
    gold_all = {}
    for split in ("dev", "holdout"):
        p = PRIV / f"{split}-answers.json"
        gold_all[split] = json.loads(p.read_text()) if p.exists() else {}

    viol = lint(gold_all)
    if viol:
        report = PRIV / "lint-report.log"
        with report.open("a") as fh:
            fh.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} (gate {mode})\n")
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
        gold = gold_all["holdout"]
        split_pred = pred_root / "holdout"
        contracts = REPO / "eval" / "holdout" / "contracts"
    else:
        gold = gold_all["dev"]
        if mode == "dev":
            ws = set(json.loads((REPO / "eval" / "dev" / "working-set.json").read_text()))
            gold = {d: e for d, e in gold.items() if d in ws}
        split_pred = pred_root / "dev"
        contracts = REPO / "eval" / "dev" / "contracts"

    # 1. macro-F1
    per_cat, _ = score_split(split_pred, gold, cats)
    mf = macro_f1(per_cat)

    # 2. quote grounding
    g, n, misses = grounding(split_pred, contracts, doc_ids=set(gold))

    # 3. High-severity precision
    tp, fp = high_severity_precision(split_pred, gold, load_severity())

    # 4. probe gap (dev-sample vs probe macro-F1, same doc cohort)
    gap = None
    probe_p = PRIV / "probe-answers.json"
    probe_pred = pred_root / "probe"
    if probe_p.exists() and probe_pred.is_dir():
        gold_probe = json.loads(probe_p.read_text())
        per_cat_probe, _ = score_split(probe_pred, gold_probe, cats)
        mf_probe = macro_f1(per_cat_probe)
        dev_ids = {k.split("-probe")[0] for k in gold_probe}
        gold_dev_sub = {d: gold_all["dev"][d] for d in dev_ids if d in gold_all["dev"]}
        per_cat_dev, _ = score_split(pred_root / "dev", gold_dev_sub, cats)
        gap = macro_f1(per_cat_dev) - mf_probe

    if mode == "holdout":
        with (PRIV / "holdout-calls.log").open("a") as fh:
            fh.write(f"{time.time()},{mf:.4f}\n")

    results = evaluate_bars(
        macro_f1_value=mf,
        grounded=g,
        grounding_total=n,
        high_tp=tp,
        high_fp=fp,
        probe_gap=gap,
    )
    print(f"EVAL GATE — {mode} ({len(gold)} docs) — predictions: {pred_root}")
    for name, val, bar, ok in results:
        print(f"  {'PASS' if ok else 'FAIL':4}  {name:20} {val:22} bar {bar}")
    if n == 0:
        print("  note: zero predicted findings — grounding/precision vacuous, counted as FAIL")
    if misses:
        print(f"  first {len(misses)} ungrounded spans (doc, category, head):")
        for d, c, s in misses:
            print(f"    {d}  {c}  {s!r}")
    if all(ok for *_, ok in results):
        print("GATE: PASS (all four criteria)")
        sys.exit(0)
    failed = [name for name, *_ , ok in results if not ok]
    print(f"GATE: FAIL — {', '.join(failed)}")
    sys.exit(1)


if __name__ == "__main__":
    main()

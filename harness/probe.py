"""Probe generator: perturbed variants of a seeded sample of dev contracts.

Entity-swaps party names and reflows whitespace. Writes probe inputs into the
repo and transformed gold answers into the private dir. The dev-vs-probe score
gap is the memorization gauge. Deterministic (fixed seed).
"""
import json, random, re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRIV = Path.home() / ".dd-eval-private"
SAMPLE = 40
SEED = 991

FAKE = ["Halcyon Industries", "Bluewater Holdings plc", "Meridian Labs Inc.",
        "Kestrel Partners LLC", "Northgate Systems Ltd", "Vantage Dynamics Corp.",
        "Silverbirch Group", "Redquay Technologies", "Amberfield Co.", "Stonebrook LLC"]

def reflow(text):
    return re.sub(r"[ \t]+", " ", text)

def main():
    gold = json.loads((PRIV / "dev-answers.json").read_text())
    rng = random.Random(SEED)
    ws = REPO / "eval" / "dev" / "working-set.json"
    ids = sorted(json.loads(ws.read_text())) if ws.exists() else sorted(gold.keys())
    rng.shuffle(ids)
    sample = ids[:SAMPLE]
    outdir = REPO / "eval" / "probe" / "contracts"
    outdir.mkdir(parents=True, exist_ok=True)
    for stale in outdir.glob("*.txt"):
        stale.unlink()
    probe_gold = {}
    for doc_id in sample:
        src = (REPO / "eval" / "dev" / "contracts" / f"{doc_id}.txt").read_text()
        parties = [p.strip() for p in gold[doc_id]["gold"].get("Parties", []) if len(p.strip()) > 3]
        # longest-first so substrings don't clobber
        parties = sorted(set(parties), key=len, reverse=True)[:len(FAKE)]
        mapping = {p: FAKE[i] for i, p in enumerate(parties)}
        text = src
        for old, new in mapping.items():
            text = text.replace(old, new)
        text = reflow(text)
        (outdir / f"{doc_id}.txt").write_text(text)
        g2 = {}
        for cat, spans in gold[doc_id]["gold"].items():
            ns = []
            for s in spans:
                t = s
                for old, new in mapping.items():
                    t = t.replace(old, new)
                ns.append(re.sub(r"[ \t]+", " ", t))
            g2[cat] = ns
        probe_gold[doc_id] = {"title": gold[doc_id]["title"], "gold": g2}
    (PRIV / "probe-answers.json").write_text(json.dumps(probe_gold, indent=0))
    print(f"probe set: {len(sample)} contracts -> {outdir}")
    print("run the pipeline on eval/probe/contracts -> predictions/probe, then: harness/score.sh probe")

if __name__ == "__main__":
    main()

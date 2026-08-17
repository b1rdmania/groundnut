"""Rebuild the eval corpus from CUAD. 🥜

Groundnut does not redistribute contract text. The eval corpus is CUAD v1
(The Atticus Project, CC BY 4.0); this script reconstructs it locally from a
CUADv1.json you supply, using eval/CORPUS-MANIFEST.json to map each contract
to its Groundnut filename and verify it byte-for-byte.

    # 1. get CUADv1.json — https://github.com/TheAtticusProject/cuad
    # 2. rebuild dev + holdout, then regenerate probe
    python3 scripts/fetch_corpus.py --cuad /path/to/CUADv1.json
    python3 harness/probe.py

Verification is against the manifest's raw sha256. Exit 0 means every supplied
contract exactly matches the corpus version the manifest was built from and
the written files are byte-identical to it.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "eval" / "CORPUS-MANIFEST.json"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Rebuild the Groundnut eval corpus from CUAD.")
    ap.add_argument("--cuad", required=True, type=Path, help="path to CUADv1.json")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    if not args.cuad.exists():
        sys.exit(f"CUADv1.json not found: {args.cuad}")
    if not MANIFEST.exists():
        sys.exit(f"manifest missing: {MANIFEST}")

    manifest = json.loads(MANIFEST.read_text())["contracts"]

    # title -> full contract text, keyed the way the manifest was built
    by_title = {}
    for item in json.loads(args.cuad.read_text())["data"]:
        by_title[item["title"]] = " ".join(p["context"] for p in item["paragraphs"])

    written = missing = mismatched = 0
    for stem, entry in sorted(manifest.items()):
        title = entry.get("cuad_title")
        text = by_title.get(title) if title else None
        if text is None:
            print(f"  MISSING  {entry['split']}/{stem}  ({title})")
            missing += 1
            continue

        expected = entry.get("sha256_raw")
        if not expected or digest(text) != expected:
            print(f"  HASH MISMATCH  {entry['split']}/{stem}  ({title})")
            mismatched += 1
            continue

        dest = REPO / "eval" / entry["split"] / "contracts" / f"{stem}.txt"
        if dest.exists() and digest(dest.read_text(errors="replace")) == expected:
            written += 1
            continue

        if args.dry_run:
            print(f"  would write  {dest.relative_to(REPO)}")
            written += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        if digest(dest.read_text(errors="replace")) != expected:
            print(f"  MISMATCH {dest.relative_to(REPO)}")
            mismatched += 1
        else:
            written += 1

    total = len(manifest)
    print(f"\n{written}/{total} contracts in place · {missing} missing · {mismatched} mismatched")
    if missing or mismatched:
        print("\nThe corpus is incomplete — scores from it are not comparable.")
        return 1
    print("Corpus verified. Next: python3 harness/probe.py  (regenerates eval/probe, seed 991)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

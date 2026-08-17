import argparse
import json
import random
from pathlib import Path

from pipeline.backends import get_backend
from pipeline.chunking import chunk_text
from pipeline.extract import filter_verbatim, merge_findings, parse_response
from pipeline.prompt import build_prompt

REPO = Path(__file__).resolve().parent.parent


def load_categories():
    return json.loads((REPO / "eval" / "categories.json").read_text())


def process_contract(path, categories, backend):
    text = path.read_text(errors="ignore")
    doc_id = path.stem
    chunk_results = []
    for chunk in chunk_text(text):
        prompt = build_prompt(categories, chunk)
        raw = backend.complete(prompt, doc_id=doc_id)
        parsed = parse_response(raw)
        chunk_results.append(filter_verbatim(parsed, chunk))
    return merge_findings(chunk_results, categories)


def build_argparser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", required=True)
    ap.add_argument("--out", dest="out_dir", required=True)
    ap.add_argument("--sample", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--backend", default=None)
    return ap


def main(argv=None):
    args = build_argparser().parse_args(argv)

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("*.txt"))
    if args.sample is not None:
        rng = random.Random(args.seed)
        files = sorted(rng.sample(files, min(args.sample, len(files))))

    categories = load_categories()
    backend = get_backend(args.backend)

    for f in files:
        outp = out_dir / (f.stem + ".json")
        if outp.exists():
            continue
        findings = process_contract(f, categories, backend)
        (out_dir / (f.stem + ".json")).write_text(json.dumps({"findings": findings}))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

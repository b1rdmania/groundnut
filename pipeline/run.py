import argparse
import json
import random
from pathlib import Path

from pipeline.backends import get_backend
from pipeline.chunking import chunk_text
from pipeline.extract import filter_verbatim, merge_findings, parse_response
from pipeline.prompt import build_prompt
from groundnut.domain import DomainPack
from groundnut.engine import analyse_text

REPO = Path(__file__).resolve().parent.parent


def load_categories():
    return json.loads((REPO / "eval" / "categories.json").read_text())


def process_contract(path, categories, backend, domain=None):
    if domain is not None:
        return analyse_text(
            path.read_text(errors="ignore"),
            source_id=path.stem,
            domain=domain,
            backend=backend,
        ).findings
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
    ap.add_argument(
        "--domain-pack",
        type=Path,
        default=None,
        help="versioned Groundnut domain-pack JSON; default keeps the legacy evaluation job",
    )
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

    domain = DomainPack.from_json(args.domain_pack) if args.domain_pack else None
    categories = domain.category_names if domain else load_categories()
    backend = get_backend(args.backend)

    for f in files:
        outp = out_dir / (f.stem + ".json")
        if outp.exists():
            continue
        if domain is None:
            payload = {"findings": process_contract(f, categories, backend)}
        else:
            result = analyse_text(
                f.read_text(errors="ignore"),
                source_id=f.stem,
                domain=domain,
                backend=backend,
            )
            payload = result.to_dict()
        (out_dir / (f.stem + ".json")).write_text(json.dumps(payload))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
USAGE_LOG = REPO / "runs" / "usage.jsonl"


def log_usage(backend, model, in_tokens, out_tokens, doc):
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "backend": backend,
        "model": model,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "doc": doc,
    }
    with USAGE_LOG.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def approx_tokens(text):
    return max(1, len(text) // 4)


class Backend:
    name = "base"
    model = "unset"

    def complete(self, prompt, doc_id=None):
        raise NotImplementedError

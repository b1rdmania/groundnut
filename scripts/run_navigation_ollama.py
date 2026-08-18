#!/usr/bin/env python3
"""Run a strict TreeDex-style navigation arm against a local Ollama model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from groundnut.adapters.navigation import TreeDexStyleNavigator  # noqa: E402
from groundnut.navigation_cases import load_navigation_pack  # noqa: E402
from groundnut.navigation_eval import run_navigation_evaluation  # noqa: E402


class OllamaJSONSelector:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        context_tokens: int,
        timeout_seconds: int,
        seed: int,
        max_output_tokens: int,
        max_nodes: int,
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.context_tokens = context_tokens
        self.timeout_seconds = timeout_seconds
        self.seed = seed
        self.max_output_tokens = max_output_tokens
        self.max_nodes = max_nodes

    def __call__(self, prompt: str) -> dict:
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": {
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": self.max_nodes,
                        },
                    },
                    "required": ["node_ids"],
                    "additionalProperties": False,
                },
                "think": False,
                "options": {
                    "temperature": 0,
                    "seed": self.seed,
                    "num_ctx": self.context_tokens,
                    "num_predict": self.max_output_tokens,
                },
            }
        ).encode()
        request = Request(
            f"{self.url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.loads(response.read())
        parsed = json.loads(result["response"])
        if not isinstance(parsed, dict):
            raise ValueError("Ollama selector response must be an object")
        return {
            **parsed,
            "input_tokens": int(result.get("prompt_eval_count", 0)),
            "output_tokens": int(result.get("eval_count", 0)),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--ollama-version", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--context-tokens", type=int, default=32768)
    parser.add_argument("--max-prompt-characters", type=int, default=100000)
    parser.add_argument("--max-nodes", type=int, default=5)
    parser.add_argument("--max-output-tokens", type=int, default=128)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--seed", type=int, default=991)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    selector = OllamaJSONSelector(
        url=args.ollama_url,
        model=args.model,
        context_tokens=args.context_tokens,
        timeout_seconds=args.timeout_seconds,
        seed=args.seed,
        max_output_tokens=args.max_output_tokens,
        max_nodes=args.max_nodes,
    )
    navigator = TreeDexStyleNavigator(
        selector,
        model=args.model,
        revision=args.model_revision,
        package_version=f"ollama-{args.ollama_version}",
        max_nodes=args.max_nodes,
        max_prompt_characters=args.max_prompt_characters,
        max_output_tokens=args.max_output_tokens,
        runtime_configuration={
            "backend": "ollama",
            "backend_version": args.ollama_version,
            "context_tokens": args.context_tokens,
            "temperature": 0,
            "seed": args.seed,
            "think": False,
            "response_format": "json-schema/v1",
        },
    )
    result = run_navigation_evaluation(
        load_navigation_pack(args.pack),
        args.corpus_root,
        (navigator,),
        progress=lambda completed, total, case_id, adapter, status: print(
            f"[{completed}/{total}] {case_id} {adapter} {status}", flush=True
        ),
        workers=args.workers,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": result["summaries"][0],
                "sha256": result["sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Resource-limited subprocess entry point for untrusted PDF extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .sources import _pdf_to_text_and_pages


SCHEMA = "groundnut-pdf-worker-result/v1"


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("limit must be positive")
    return parsed


def _apply_limits(*, cpu_seconds: int, memory_bytes: int, output_bytes: int) -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (output_bytes, output_bytes))
    if hasattr(resource, "RLIMIT_AS"):
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (OSError, ValueError):
            # macOS counts enormous shared address mappings against RLIMIT_AS.
            # The parent independently enforces the resident-memory ceiling.
            pass
    if hasattr(resource, "RLIMIT_NOFILE"):
        current, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        descriptor_limit = min(32, hard) if hard >= 0 else 32
        resource.setrlimit(
            resource.RLIMIT_NOFILE, (descriptor_limit, descriptor_limit)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--max-input-bytes", required=True, type=_positive)
    parser.add_argument("--max-pages", required=True, type=_positive)
    parser.add_argument("--max-characters", required=True, type=_positive)
    parser.add_argument("--cpu-seconds", required=True, type=_positive)
    parser.add_argument("--memory-bytes", required=True, type=_positive)
    parser.add_argument("--max-output-bytes", required=True, type=_positive)
    args = parser.parse_args(argv)

    _apply_limits(
        cpu_seconds=args.cpu_seconds,
        memory_bytes=args.memory_bytes,
        output_bytes=args.max_output_bytes,
    )
    if args.input is None:
        data = sys.stdin.buffer.read(args.max_input_bytes + 1)
    else:
        with args.input.open("rb") as source:
            data = source.read(args.max_input_bytes + 1)
    if len(data) > args.max_input_bytes:
        payload = {
            "schema": SCHEMA,
            "status": "error",
            "detail": "pdf_input_exceeds_limit",
        }
    else:
        text, total_pages, character_truncated = _pdf_to_text_and_pages(
            data,
            max_pages=args.max_pages,
            max_characters=args.max_characters,
        )
        payload = (
            {
                "schema": SCHEMA,
                "status": "ok",
                "text": text,
                "total_pages": total_pages,
                "character_truncated": character_truncated,
            }
            if text is not None and total_pages is not None
            else {
                "schema": SCHEMA,
                "status": "error",
                "detail": "application/pdf: no text layer or no extractor",
            }
        )
    Path(args.out).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

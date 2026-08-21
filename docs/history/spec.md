# Spec — DD red-flag extraction pipeline (inner loop)

The system under construction: a CLI pipeline that reads a contract and emits
structured findings across the 41 CUAD clause categories (`eval/categories.json`).
This is the extraction core; it will later sit
under the Legalise sign-off/audit layer (see `backend/app/core/retrieval.py` and
the audit machinery in the Legalise repo for the eventual integration surface —
do NOT import Legalise code during the optimization run; keep this repo
self-contained).

## Interface (fixed — the harness depends on it)

```
python3 -m pipeline.run --in eval/dev/contracts --out predictions/dev [--sample N] [--seed S]
```

- Reads every `*.txt` in `--in` (or a seeded sample of N).
- Writes one `predictions/<split>/<doc_id>.json` per contract:

```json
{"findings": {"<Category Name>": ["verbatim quote from the contract", ...], ...}}
```

- A category with no clause present is omitted or maps to `[]`.
- Quotes MUST be verbatim substrings of the source contract (the scorer
  fuzzy-matches, but fabricated text scores zero).
- Every model call appends one line to `runs/usage.jsonl`:
  `{"backend": "...", "model": "...", "in_tokens": N, "out_tokens": N, "doc": "..."}`

## Backend abstraction (design call: model-agnostic)

`pipeline/backends/` with a common `complete(prompt) -> text` interface:

- `openai_compat` — any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM,
  LiteLLM proxy). Base URL + model from env `DD_BASE_URL` / `DD_MODEL`. This is
  the production track; nothing in the pipeline may assume a specific vendor.
- `agent` — task-file protocol: the CLI writes pending extraction prompts to
  `runs/tasks/pending/*.json`; the supervising agent completes them into
  `runs/tasks/done/*.json`; the CLI collects. This is the subscription-run mode.
- `stub` — deterministic canned responses, for tests only.

## Inner-loop test suite (Stage 0 gate — all green before any eval descent)

`tests/` (pytest, no network, stub backend):
1. Round-trip: pipeline on a fixture contract produces valid JSON in the
   output contract shape.
2. Verbatim rule: every emitted quote is a substring of the input.
3. Empty/absent categories handled (omitted or `[]`, never null/prose).
4. Chunking: a contract longer than the model context is chunked and findings
   are merged without duplication.
5. Usage logging: one usage line per model call.
6. Backend swap: same fixture through `stub` and a mocked `openai_compat`
   yields shape-identical output.

## Out of scope for the loop

Sign-off UI, register integration, severity ranking, missing-document
detection, report generation. The loop optimizes recall/precision of clause
extraction only.

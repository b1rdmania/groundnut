# Groundnut 🥜

Contract in, red flags out — every one carrying a quote you can find in the source.

Groundnut is the extraction engine and its eval harness. Two halves:

- **🥜 Shell** — `pipeline/`. Reads a contract, returns findings by category, each with a verbatim quote.
- **🌰 Kernel** — `harness/`. Scores the findings. Deterministic, four criteria, one exit code. No LLM anywhere on the pass/fail path.

The name is the job: everything here is about whether a finding is *grounded* — whether the quote it rests on actually exists in the document.

## Corpus 📚

**Groundnut does not ship contract text.** The eval corpus is [CUAD v1](https://github.com/TheAtticusProject/cuad) (The Atticus Project, CC BY 4.0) — 510 contracts across dev and holdout. Rebuild it locally:

```bash
python3 scripts/fetch_corpus.py --cuad /path/to/CUADv1.json   # dev + holdout
python3 harness/probe.py                                      # probe, seed 991
```

`eval/CORPUS-MANIFEST.json` maps every Groundnut filename to its CUAD title and verifies each one by hash, so the corpus you rebuild is byte-identical to the one the scores below were measured on.

Gold answers are **not** in this repo at all — they live in `~/.dd-eval-private/`. That is what makes the holdout rate-limit mean something.

## Run it

```bash
python3 -m pytest tests/          # inner loop — keep green
harness/gate.sh dev               # four-criteria gate, 80 docs
harness/gate.sh dev --pred-root runs/predictions-claude-opus-4.8-agent
```

Holdout is rate-limited to one run per 6 hours and is **currently unspent**. Don't spend it until something passes dev.

## The gate 🚦

| # | Criterion | Bar | Judge |
|---|---|---|---|
| 1 | macro-F1 | ≥ 0.55 | `score.py` |
| 2 | quote-grounding | ≥ 0.95 | `judges.py` |
| 3 | High-severity precision | ≥ 0.70 | `judges.py` |
| 4 | probe gap (overfitting guard) | ≤ +0.05 | `gate.py` |

All four are deterministic. A model never decides whether a run passes.

## Where it stands 📊

Best recorded run (`runs/predictions-claude-opus-4.8-agent`, dev-80):

| Criterion | Value | |
|---|---|---|
| macro-F1 | 0.4916 | ❌ |
| quote-grounding | 0.9744 | ✅ |
| High-severity precision | 0.6834 | ❌ (8 findings short) |

**GATE: FAIL.** That is the honest state and it stays in the README until it isn't.

### On the grounding number ⚠️

Filtered runs score 1.0000 on quote-grounding, and that figure is **worth nothing on its own** — `pipeline/extract.py` drops any span that isn't an exact substring of its source before findings are recorded. On a filtered run, grounding is 1.0 by construction. It measures the filter.

The number that means something comes from the runs with **no** verbatim filter: **0.9744** (Opus 4.8) and **0.9665** (Sonnet 5). So there are two separate claims, and they should never be merged:

- **Architectural** — the pipeline cannot emit an ungrounded quote. Unmatched spans are dropped at extraction. A design guarantee, not evidence about the model.
- **Empirical** — unfiltered, frontier models return verbatim quotes **~97%** of the time. The remaining ~3% is what the filter exists for.

Both are provenance claims, not truth claims: retrieval can be incomplete, a source can be wrong, and a correctly-quoted span can still be the wrong span.

Caveat on the ~97%: it comes from agent runs (whole-document context, no temperature pinning, non-API protocol) that `LOG.md` calls *indicative, not API-reproducible*. It has not been established under a reproducible API run.

Full measurement notes, including two corrected results and what to attack: [`FINDINGS.md`](./FINDINGS.md).

## Open questions 🔍

**Is criterion 1 measuring the right thing?** The matcher is a symmetric token-set Jaccard at 0.5, which punishes a correct extraction for choosing different span boundaries than the annotator. Swapping it for containment moves the best run 0.4916 → 0.6415 **and raises precision 0.630 → 0.824** — the sign that the "false positives" were mostly boundary mismatches, not errors. Containment is also what LegalBench-RAG uses to score spans.

⚠️ Not adopted yet, and not adoptable casually: an eval whose owner swaps the metric until it passes has destroyed the only thing that made it worth having. If containment is adopted, the 0.55 bar must be **re-derived under the new matcher and written down before re-scoring**. Passing an old bar with a new metric is not a result.

**When should the chunker fire?** Cycle 7 measured the same model at 0.4067 chunked vs 0.5721 whole-document — chunking costs more precision than the gap between model tiers. The chunker exists as a tail safety net for contracts longer than the context window (p90 ≈ 30K tokens, max seen ≈ 85K). Against a 1M-context model it should essentially never fire. Raise the threshold; don't delete the path. Its merge behaviour on the largest real contracts is still unverified.

## Layout 🗂️

```
pipeline/     🥜 the extractor — CLI, backends, chunker, prompt, verbatim filter
harness/      🌰 the gate — gate.py, judges.py, score.py, severity.json
eval/         📚 41 categories, dev / holdout / probe splits
tests/        ✅ inner-loop suite, must be green before any eval descent
runs/         📦 cached predictions per model (gitignored)
spec.md       📐 what pipeline/ must implement
goal.md       🎯 cycle protocol, entropy rules, stop conditions
LOG.md        📓 one entry per cycle — question, result, findings
```

## Who uses it 🔌

Groundnut is the engine. Things built on it live elsewhere and call in:

- **Legalise** — the governance layer: human sign-off and a tamper-evident audit trail. Groundnut's extraction plumbing is ported into its `modules/diligence/`.
- **Atlas**, **dealroom** — Legalise deployments.

Groundnut has no auth, no database, no UI, and should never grow one. It reads a contract and scores the result. 🥜

## Licence & attribution ⚖️

Code is Apache 2.0 — see [`LICENSE`](./LICENSE).

The eval corpus is **CUAD v1**, © The Atticus Project, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). It is not redistributed here; `scripts/fetch_corpus.py` rebuilds it from a copy you obtain yourself.

> Hendrycks, Burns, Chen & Ball. *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review.* NeurIPS 2021.

**Publish numbers, never data.** Scores computed on this corpus are ours to report; the contract text is the Atticus Project's to distribute.

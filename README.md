# Groundnut 🥜

Sources and a checklist in; anchored findings and an honest coverage record out.

Groundnut is the canonical anti-hallucination and checking engine: a
checklist-driven document-intelligence method plus the machinery that tests its
claims. Change the domain pack and the same method can review contracts,
procurement files, trust instruments, or another document set:

- **Canonical engine** — `groundnut/`. Domain packs, exact source anchors,
  fail-closed coverage, source snapshots, and the adversarial arena.
- **Domain packs** — `domains/`. Versioned checklists with explicit evidence
  maturity; configuration portability never implies measured quality.
- **Compatibility pipeline** — `pipeline/`. The original contract-extraction
  CLI and backend adapters.
- **Evaluation kernel** — `harness/`. Deterministic scoring and gates; no LLM
  on the pass/fail path.

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

# canonical domain-pack run
python3 -m pipeline.run --domain trust_obligations --in contracts --out results

# offline adversarial adjudication: 0 pass, 1 reviewed/non-pass, 2 bad input
python3 -m groundnut.arena_cli --policy policies/canonical-arena-v1.json \
  --tasks tasks.jsonl --attacks attacks.jsonl --rulings rulings.jsonl \
  --out arena-report.json
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

The unfiltered agent runs score **0.9744** (Opus 4.8) and **0.9665**
(Sonnet 5) under the judge's *normalised* substring rule. Exact substring rates
are lower: **0.9283** and **0.9070**. These claims must remain separate:

- **Architectural** — the pipeline cannot emit an ungrounded quote. Unmatched spans are dropped at extraction. A design guarantee, not evidence about the model.
- **Empirical** — unfiltered agent outputs are grounded about **97% under the
  normalised judge**, but exactly verbatim about **91–93%** of the time.

Both are provenance claims, not truth claims: retrieval can be incomplete, a source can be wrong, and a correctly-quoted span can still be the wrong span.

Caveat: both rates come from agent runs (whole-document context, no temperature
pinning, non-API protocol) that `LOG.md` calls *indicative, not
API-reproducible*. Neither has been established under a reproducible API run.

Full measurement notes, including the independent-review corrections and what
to attack: [`FINDINGS.md`](./FINDINGS.md).

## Open questions 🔍

**Is criterion 1 measuring the right thing?** The matcher is a symmetric
token-set Jaccard at 0.5, which may punish different span boundaries. An early
containment sweep reported `0.6415`, but the scorer does not enforce one-to-one
prediction/gold matching. Enforcing one-to-one matching reduces that result to
`0.5661`. The earlier precision increase is not evidence of correctness: a
more permissive matcher applied to fixed predictions necessarily converts some
false positives into true positives.

⚠️ Not adopted yet, and not adoptable casually: an eval whose owner swaps the metric until it passes has destroyed the only thing that made it worth having. If containment is adopted, the 0.55 bar must be **re-derived under the new matcher and written down before re-scoring**. Passing an old bar with a new metric is not a result.

**When should the chunker fire?** It currently fires on `347/510` contracts
and `56/80` working-set contracts, producing a mean `3.18` and maximum `18`
chunks. The observed precision gap between a chunked API run and a
whole-document agent run is suggestive but confounded by protocol and coverage.
Run the same backend and cohort with only the threshold changed before making a
causal claim. Keep the long-document path; its merge behaviour on the largest
real contracts remains unverified.

## Layout 🗂️

```
groundnut/     🥜 canonical domain engine, coverage, provenance, sources, arena
domains/       🧭 versioned checklists and evidence disclosures
policies/      🧊 frozen arena policy
pipeline/     🥜 the extractor — CLI, backends, chunker, prompt, verbatim filter
harness/      🌰 the gate — gate.py, judges.py, score.py, severity.json
eval/         📚 41 categories, dev / holdout / probe splits
tests/        ✅ inner-loop suite, must be green before any eval descent
runs/         📦 cached predictions per model (gitignored)
spec.md       📐 what pipeline/ must implement
goal.md       🎯 cycle protocol, entropy rules, stop conditions
LOG.md        📓 one entry per cycle — question, result, findings
```

## Relationship to downstream work 🔌

Groundnut is the engine, not a shared folder subordinate to a current product.
IC research is a future proving ground once the core is tight. Product v2s,
operating-system ports, and open-source packaging are optional later decisions,
not present milestones.

Groundnut has no auth, application database, or UI. Hosts own those concerns;
Groundnut owns the portable method, provenance, and evaluation contracts. Its
boundary is recorded in [`ARCHITECTURE.md`](./ARCHITECTURE.md), and any future
host replacement must first satisfy [`PARITY.md`](./PARITY.md). 🥜

## Licence & attribution ⚖️

Code is Apache 2.0 — see [`LICENSE`](./LICENSE).

The eval corpus is **CUAD v1**, © The Atticus Project, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). It is not redistributed here; `scripts/fetch_corpus.py` rebuilds it from a copy you obtain yourself.

> Hendrycks, Burns, Chen & Ball. *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review.* NeurIPS 2021.

**Publish numbers, never data.** Scores computed on this corpus are ours to report; the contract text is the Atticus Project's to distribute.

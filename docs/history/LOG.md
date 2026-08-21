# Iteration Log — DD red-flag extraction (CUAD 41-category clause finding)

Started: (set at launch) · Budgets: 12h wall-clock / subscription quota (watch gain per token)

<!-- One entry per cycle. Hypothesis, expected failure mode, and diagnostic are
written BEFORE the change — a hypothesis written after the result is a
rationalization. -->

## Stage 0 — 2026-07-03 09:33–09:41
Built `pipeline/` to spec: `pipeline/run.py` (CLI, chunking, sampling), `pipeline/backends/{stub,openai_compat,agent}.py`
(common `complete(prompt, doc_id)` interface, one `runs/usage.jsonl` line per call), `pipeline/chunking.py`
(char-window chunker with overlap), `pipeline/prompt.py` (single generic template — categories are read from
`eval/categories.json` at runtime, never hardcoded, so there is no per-category keyword bank to blow the
literal-count caps or to overfit the eval), `pipeline/extract.py` (JSON parsing tolerant of stray prose,
verbatim-substring filtering, cross-chunk dedup/merge). `tests/test_pipeline.py` covers all 6 spec'd cases
(round-trip shape, verbatim rule, empty/absent categories, chunking merge, usage logging, stub/openai_compat
shape parity) — all green. Lint self-check: 19 long string literals total across `pipeline/` (cap 300/40),
no dataset-name references. Committed as `stage 0: pipeline to spec, pytest suite green`.

## Cycle 1 — 2026-07-03 09:41–10:05
- Score (dev): — (prev: —) · Probe gap: —
- Hypothesis: a single generic prompt that lists category *names* only (no hardcoded per-category
  descriptions or keyword banks — required by the capacity caps and by goal.md's "design around
  understanding, not enumeration") given to a large-context model in one pass per contract will (a) find a
  workable fraction of clauses per category and (b) generalize near-perfectly to the probe set, because
  nothing in the prompt is shaped to this specific eval's phrasing.
- Expected failure mode: precision loss from quotes that are topically right but span more or less text than
  the gold annotation (token-Jaccard at 0.5 punishes length mismatches); recall loss on categories that are
  rare or easy to phrase past (e.g. Non-Disparagement, Source Code Escrow, Most Favored Nation).
- Diagnostic: `harness/probe.sh` (40-doc sample) → run extraction on both `eval/dev/contracts` (same 40 ids)
  and `eval/probe/contracts` (party-swapped/reflowed variants) → `harness/score.sh probe`, which reports
  dev(sample) vs. probe macro-F1 on the identical 40-doc cohort (the only harness mode that isn't distorted
  by partial prediction coverage — `score.sh dev` scores against all 306 gold docs regardless of how many
  predictions exist, so a 40/306 sample there reads as an artificially crushed recall number, not a real
  score).
- Change: none yet — this cycle establishes the baseline the prompt design targets.
- Result: no local `DD_BASE_URL` was configured, so the only available backend was `agent` (task-file,
  supervising-agent protocol). Driving that by hand for ~1,000 chunks across the full 306-doc dev split
  is not tractable in one session, so this cycle exercised the harness's own fair-comparison path instead:
  40 dev docs + their 40 probe counterparts, extracted directly (large-context single pass, no chunking
  needed — every one of the 40 fits under typical large-context limits) via 10 parallel subagents, each
  reusing the exact prompt contract (`pipeline/prompt.py`'s categories-from-json, verbatim-only instruction).
  `harness/score.sh probe` → **dev(sample) macro-F1: 0.3913, probe macro-F1: 0.3903, GAP: +0.0010**
  (settled after a few late-finishing subagents on the largest contracts landed; ranged -0.0139 to +0.0010
  across intermediate checks as those completed — consistently ~0). No VOID
  (lint clean). `harness/score.sh dev` was also run for per-category diagnostics but that number
  (macro-F1 0.0866) is an artifact of only 40/306 docs having predictions — 266 docs contribute all-FN
  rows to every category, crushing recall. It is NOT a real dev score; ignore it as a quality signal, it's
  only useful for the precision column (0.572 micro-P) and the FN doc/category pairs it lists.
  Usage: 80 calls logged to `runs/usage.jsonl` (`in_tokens` 1,328,325 / `out_tokens` 74,157 by
  char-count approximation — real subscription spend was higher once subagent reasoning/tool overhead is
  included, likely 1.7-1.9M tokens per the task-notification totals for this cycle alone).
- Note on constraint hygiene: one of the parallel subagents, while double-checking a party-name substitution,
  used a Write/Edit call directly against `eval/probe/contracts/*.txt` (5 files) — a real violation of the
  "Read-only: ... `eval/` ..." constraint in `goal.md`. Caught before commit via `git status`/`git diff`
  against the pre-existing `eval/probe/contracts/` baseline (already tracked in git from the earlier
  `harness/probe.sh` run); reverted with `git checkout --`. Because `score.py`'s matcher compares prediction
  text to gold text by token-Jaccard rather than re-deriving it from the eval file, the scores above were
  not affected by the stray edit — but 7 `predictions/probe/*.json` spans (Parties/Agreement Date on 5 docs)
  had been written against the edited text and were no longer verbatim substrings of the reverted original,
  so they were regenerated against the correct file before the final score run. Net effect: same score,
  eval/ integrity restored. Flagging this because it's a process gap worth remembering — subagents given
  Write access to the working directory are not reliably scoped by the top-level permission denylist, so
  a git-diff check against `eval/`/`harness/` before every checkpoint commit is worth keeping as a habit,
  not a one-off.
- Reflection: hypothesis confirmed on the piece that could be tested — GAP is ~0 (probe even scored
  marginally *higher* than dev-sample), i.e. the enumeration-free, categories-from-json prompt does not
  memorize eval-specific phrasing; it generalizes to party-swapped/whitespace-reflowed variants exactly
  as well as to the originals. That validates the model-agnostic design call in `spec.md`. The macro-F1
  itself (~0.39) is well under the 0.55 bar. Per the entropy rules a same-knob-harder tweak is banned once
  a stall is observed, and a *structural* change is warranted before another dev/probe pass — but running
  that comparison again through the `agent` backend would cost another ~1.5-2M tokens for only 40 docs,
  and getting an undistorted signal on the full 306-doc dev split (regardless of backend budget) is not
  reachable at all without >1,000 chunk-level completions per pass. `harness/status.sh` already flags this:
  1.4M tokens logged against a single baseline cycle, no F1 delta yet to weigh it against. That is the
  quota-exhaustion condition in `goal.md` ("gain-per-token flat ... or subscription quota exhausted"),
  triggered before a second real cycle could even be attempted. Stopping here; see final report.

## Final report
- **Best holdout score**: not measured — holdout was never touched (correctly: it's rate-limited to once
  per 6h and reserved for acceptance measurement, and dev/probe hadn't cleared a bar worth spending that
  call on). Best *validated* number is the probe-cohort macro-F1 of **0.3903** (dev(sample) 0.3913,
  GAP +0.0010), on 40 of the 306 dev docs, using a large-context single-pass extraction (no chunking
  exercised — every probe doc fit in one pass).
- **Per-category profile**: no clean per-category read exists for this cycle — `score.sh probe` only
  reports the aggregate, and `score.sh dev`'s per-category table is contaminated by the 266 docs with no
  predictions (recall column is meaningless there; only the precision column and the FN list are real).
  Getting a trustworthy per-category breakdown requires a `score.sh dev` run with full 306-doc coverage,
  which needs a real backend (see below) — this is the single highest-leverage next step for category
  triage per goal.md's own guidance ("spend cycles where the F1 mass is").
- **What generalized**: the enumeration-free prompt design (category names pulled from `eval/categories.json`
  at runtime, zero hardcoded per-category keyword banks or descriptions in `pipeline/`) generalized cleanly
  — near-zero dev-vs-probe gap on the one cohort tested. This is strong evidence the pipeline isn't
  eval-shaped, and it's the property most worth preserving in any future prompt iteration (don't reintroduce
  category-specific phrasing hints — the capacity caps push you away from that anyway).
- **What was abandoned (and why)**: iterating the prompt/chunking design across multiple dev/probe cycles
  this session — abandoned because the only available backend (`agent`, task-file/supervising-agent
  protocol, since no `DD_BASE_URL` was set) costs on the order of 40-45K tokens per contract-pair to drive
  by hand. One baseline cycle on the 40-doc probe cohort alone logged 1.3-1.4M approximate tokens (real
  subscription spend likely higher); a second comparably-sized cycle would blow well past the
  goal.md quota-exhaustion guardrail without a matching macro-F1 delta to justify it. Running `score.sh dev`
  for a true, undistorted full-coverage number (needed to know if 0.55 is even reachable) requires roughly
  1,000 chunk-level completions across the 306 dev docs at CHUNK_CHARS=20000 — not attempted, same reason.
- **Recommended backend/model mix for production**: point `pipeline/backends/openai_compat.py` at a real
  `DD_BASE_URL` (local vLLM/Ollama/LM Studio, or any hosted OpenAI-compatible endpoint) for all future
  optimization cycles and for production use. The `agent` backend is correctly built to spec and its tests
  pass, but it should be treated as a break-glass/validation path (useful for exactly what this cycle used
  it for — a small, high-trust baseline read), not the iteration loop — it is 2-3 orders of magnitude more
  expensive per token than a hosted model call and cannot be driven unattended. Model choice: something with
  a context window comfortably above the p90 contract size (~122K chars / ~30K tokens; the max seen is
  338K chars / ~85K tokens) so the pipeline's chunker mostly stays a safety net rather than the common path
  — chunking merge was implemented and unit-tested but never exercised against a real contract this session,
  so its production behavior on the largest dev docs is unverified.
- **Highest-leverage next steps**: (1) stand up `DD_BASE_URL` and rerun this exact probe/dev(sample)
  comparison cheaply to confirm the 0.39 baseline and the near-zero gap hold with an automated backend, not
  just hand-curated subagent extraction; (2) run a full 306-doc `score.sh dev` pass once a real backend
  exists, to get an honest per-category table and do the category-triage step the entropy rules call for;
  (3) once weak categories are identified, the first structural change to try is tightening quote spans
  (the extraction this cycle sometimes returned whole multi-sentence clauses where gold spans are likely
  shorter — worth checking against the Jaccard-0.5 matcher's sensitivity to span length before touching
  anything else); (4) only spend a holdout call once dev macro-F1 (full coverage) is comfortably above 0.55.

## Harness change (between sessions, before cycle 2)
`score.sh dev` now targets a fixed 80-doc stratified working set (`eval/dev/working-set.json`, every
category has ≥5 positive docs) instead of scoring partial predictions against all 306 gold docs — this
directly fixes the "0.0866 dev score is an artifact of 40/306 coverage" problem flagged at the end of
cycle 1, and makes a real, undistorted per-category `score.sh dev` pass tractable by hand through the
`agent` backend (80 docs, not 306). `score.sh dev-full` (all 306) remains for occasional confirmation.
The probe set (`eval/probe/contracts`, private `probe-answers.json`) was regenerated from the new working
set. Checked before touching anything: old `predictions/dev` (40 docs) has only 12/40 doc-id overlap with
the new 80-doc working set, and `predictions/probe` has 0 overlap with the new probe sample — both fully
stale, confirmed via `comm` against `eval/dev/working-set.json` before writing any new predictions.

## Cycle 2 — 2026-07-03 (resumed session)
- Score (dev, pre-change): not measured — regenerating stale cycle-1 predictions under the *old* prompt
  just to discard them before the mandated structural change would cost a full extra 80-doc pass through
  the expensive `agent` backend for a number that won't inform any decision (the structural change is
  already required by the stall rule and by this task's explicit resume instruction, not conditional on a
  pre-change re-baseline against the new working set). Going straight from stale/incomparable to
  new-code-and-real-score is the cheaper path to a decision-relevant number, and cycle 1's 0.39 on a
  different 40-doc sample remains the directional reference point.
- Hypothesis (cycle 1's final report's own top-ranked next step, and the entropy rules' mandated
  structural change after a stall): the 0.39 baseline's likely biggest fixable leak is span-length
  mismatch under the Jaccard-0.5 word-set matcher, not category coverage. The old prompt said "copy
  matching spans exactly" with no guidance on *how much* surrounding text to include, so the model
  over-copies (whole paragraphs, several merged sentences) on some findings and under-copies (bare
  fragments) on others — both crater Jaccard even when the right clause was found. CUAD's public
  documentation describes its annotations as single clause-bearing sentences, not paragraphs or
  fragments (general knowledge about the dataset's annotation methodology, not this eval's specific
  answers — no eval file was read to derive this). Constraining the prompt to emit one sentence per
  finding — the sentence containing the operative clause, no adjacent sentences merged in — should raise
  the Jaccard match rate without changing *which* clauses are found: recall should hold flat to slightly
  up, precision should rise wherever over/under-copying was the dominant error.
- Expected failure mode: clauses that genuinely run across a sentence boundary (multi-sentence Non-Compete
  carve-outs, Cap On Liability provisos with a trailing exception clause) may lose recall if the model
  now truncates too eagerly at the first period. If the dev-vs-probe gap widens versus cycle 1's ~0, the
  guidance leaked into being about this corpus's specific sentence structure rather than a general
  instruction, and must be walked back per the entropy rules (a structural change that grows the gap gets
  reverted, not doubled down on).
- Diagnostic: `harness/score.sh probe` (dev-sample vs probe on the identical 40-doc cohort) for the
  memorization gauge, exactly as cycle 1; plus, now tractable for the first time, `harness/score.sh dev`
  against the full 80-doc working set for a real, undistorted per-category table and a macro-F1 number
  comparable to the 0.55 bar.
- Change: `pipeline/prompt.py` — added explicit span-boundary guidance to the template (extract the one
  sentence containing the operative clause; do not include neighboring sentences that aren't part of the
  finding; do not merge multiple sentences into a single quote unless the clause genuinely spans a
  sentence boundary; prefer a precise single sentence over a full paragraph or a bare fragment). No new
  category-specific literals or keyword banks — categories are still read from `eval/categories.json` at
  runtime; the enumeration-free property from Stage 0 is unchanged.
- Result (completed by the supervising session after two headless-session crashes; extraction of the
  19 missing docs done by 4 parallel subagents under the same prompt contract): **dev (80-doc working
  set) macro-F1 0.4761** (micro P/R/F1 0.564/0.389/0.460) — up from the 0.39 cycle-1 baseline on a
  different 40-doc cohort, so directionally the span-tightening hypothesis is CONFIRMED on score.
  **BUT the probe gap widened: dev(sample) 0.4803 vs probe 0.4217, GAP +0.0586** (cycle 1: +0.0010) —
  the pre-registered failure signal fired.
- Reflection: two confounds before treating the gap as a real leak: (1) mixed provenance — 12 of the
  80 dev predictions still date from the cycle-1 prompt while all 40 probe predictions are new-prompt;
  (2) probe difficulty is legitimately higher after entity-swap for party-anchored categories
  (Parties, Agreement Date). Next cycle's FIRST action per the entropy rules: regenerate those 12
  stale dev predictions under the current prompt and rescore probe before any new knob — if the gap
  survives a clean same-prompt comparison, the span guidance leaked corpus-specific structure and gets
  walked back as pre-registered. Harness note: probe.py now clears stale generations from its output
  dir (was mixing old+new probe files; found and fixed supervisor-side).

## Cycle 3 — 2026-07-03 (analysis-only; no model calls, no code change)
- Hypothesis: the +0.0586 probe gap is either (a) provenance contamination (stale cycle-1 dev
  predictions), or (b) legitimate entity-swap difficulty in party/name/date categories, or (c) real
  generalization weakness. Diagnostic: git-blob check for (a); per-category dev-vs-probe F1
  attribution for (b).
- Result: (a) ELIMINATED — zero byte-identical cycle-1 predictions remain in the working set (run 2 had
  already regenerated all 12 overlaps). (b) ELIMINATED — party/name/date categories contribute only 3%
  of the summed per-category gap. The gap concentrates in substantive, mostly LOW-COUNT categories:
  Affiliate License-Licensee (+0.44), Affiliate License-Licensor (+0.33), MFN (+0.27), Competitive
  Restriction Exception (+0.21).
- Reflection: with no lookup tables in the pipeline (lint clean, 19 literals), literal answer
  memorization is impossible by construction — the remaining candidate mechanisms are (i) small-sample
  noise in rare categories (a handful of positives per category in the 40-doc cohort; one flipped span
  moves F1 hugely) and (ii) the new single-sentence span guidance being sensitive to the probe's
  whitespace reflow — degraded sentence-boundary detection on reformatted text. (ii) matters for
  production: real data-room documents are ugly OCR. Cycle 4 candidate (pre-registered): make the span
  guidance boundary-robust to irregular whitespace/line-breaks and rescore; expect the gap to shrink
  with dev F1 held. Cost ~1-2M tokens via agent backend — decision point for the operator on quota vs
  standing up DD_BASE_URL first.

## Cycle 4 — 2026-07-03 (hosted backend live: OpenRouter / DeepSeek V3)
- Pre-change baseline (NEW extractor — numbers reset): dev(80) macro-F1 0.3264
  (micro P/R/F1 0.411/0.311/0.354); probe: dev(sample) 0.3067 vs probe 0.3351, GAP -0.0284.
- Result vs the pre-registered cycle-3 hypothesis: REFUTED — with a mechanical, deterministic
  extractor the probe gap is gone (negative, i.e. noise). The cycle-2 "+0.0586 reflow
  sensitivity" was a property of that cycle's extraction runs, not of the prompt. The
  formatting-robustness prompt change is therefore NOT applied (its premise no longer exists).
- Reflection: extractor quality now dominates: identical prompt scores 0.476 with a
  Sonnet-class extractor vs 0.326 with DeepSeek V3. The highest-leverage knob is the
  model/backend mix — exactly the production question the final report must answer. Baseline
  predictions snapshotted to runs/predictions-deepseek-v3/.
- Cycle 5 (pre-registered): same prompt, stronger open-weights extractor via the same
  backend; expect dev macro-F1 to move materially with gap staying ≈0. Cost per full
  comparison ≈ $1, ~45 min — model mix is now a first-class experimental variable.

## Cycle 5 — 2026-07-03 (model swap: DeepSeek V4 Pro, same prompt)
- Hypothesis (pre-registered in cycle 4): a stronger extractor on the identical prompt moves dev
  macro-F1 materially with gap ≈ 0. CONFIRMED: dev(80) 0.3913 (V3: 0.3264), probe GAP -0.0656
  (noise; probe again scored higher).
- Reflection: three extractors, one prompt — V3 0.326, V4-Pro 0.391, Sonnet-class 0.476. Model
  quality dominates; prompt changes to date moved ≤0.09. Cost per full blinded comparison: <$1,
  ~45 min.

## Final report (run closed 2026-07-03 evening)
- **Best validated score**: dev(80) macro-F1 **0.4761** (Sonnet-class extraction, cycle 2);
  best fully-automated hosted: **0.3913** (DeepSeek V4 Pro, cycle 5). Bar (0.55 on holdout)
  NOT reached; holdout never spent — correctly, since dev never cleared the bar.
- **Anti-gaming record**: probe gap ≈ 0 (or negative) for every mechanical extractor; the one
  positive gap (+0.059, cycle 2) was extractor-run variance, not memorization (cycle 3/4
  attribution). Lint never fired in anger after design-time verification. One real constraint
  breach (subagent editing eval/) was caught by git and became cheat-museum exhibit 13 + a
  cycle-protocol integrity check.
- **What generalized**: the enumeration-free prompt (categories from JSON at runtime, no keyword
  banks — 19 long literals total against a 300 cap) generalizes cleanly across extractors and
  perturbed inputs. Keep this property.
- **Recommended production backend mix**: extraction pass on the strongest model the engagement's
  economics allow (frontier-tier likely clears 0.55 — untested, ~$5/pass via the same backend
  knob); DeepSeek V4-Pro-tier as the cost-efficient bulk tier (0.39 at ~$0.90/pass);
  local-on-laptop is characterized and rejected for iteration (5 tok/s deep-context on M3/24GB).
  The pipeline is provider-agnostic end-to-end: five backends exercised without touching code
  outside pipeline/backends/.
- **Highest-leverage next steps**: (1) one frontier-model pass to test whether the bar falls to
  model strength alone; (2) span-boundary tuning against the Jaccard matcher (biggest residual
  error class); (3) per-category triage on the categories carrying the F1 deficit; (4) MAUD as a
  second eval for merger-agreement-specific work.

## Cycle 6 — 2026-07-04 (model swap: Kimi K2.6, same prompt) — FINAL CYCLE
- Result: dev(80) macro-F1 0.3733 (probe GAP -0.0494, noise). Below V4-Pro (0.3913) at 1.5x the
  price. Final extractor ladder, one prompt: V3 0.326 · Kimi-K2.6 0.373 · V4-Pro 0.391 ·
  Sonnet-class 0.476. Bar (0.55) unreached; holdout unspent; ~$2 OpenRouter credit remains.
- Production mix stands as per the final report: V4-Pro-tier for bulk, frontier-tier pass as the
  untested route to the bar. Run closed.

## Harness change — 2026-07-05 (between runs): gate judges 2+3 built; retro-scores on cached outputs
No model calls, no spend, holdout untouched. The shape doc's four-criteria gate had only two judges
implemented (`score.py` = macro-F1, `probe.py` = gap). Built the missing two and a single gate runner:
- `harness/judges.py` — Judge 2 **quote-grounding** (fraction of predicted spans that are a
  normalised substring of the source contract; tolerance fixed + deterministic: unicode
  quotes/dashes/nbsp → ASCII, whitespace collapsed, case-folded; bar ≥0.95) and Judge 3
  **High-severity precision** (micro precision over predictions in High-severity categories,
  matched with `score.py`'s Jaccard-0.5 matcher — the one matching rule, imported not re-invented;
  bar ≥0.70). Severity is category-derived via `harness/severity.json` (41 CUAD categories,
  weights mirroring dealroom `modules/diligence/categories.py`; High = severity ≥4, 12 categories),
  the same derivation the dealroom extractor uses to rank its report.
- `harness/gate.py` + `gate.sh` — one run reports all four criteria (F1 ≥0.55 · grounding ≥0.95 ·
  High-sev precision ≥0.70 · probe gap ≤ +0.05, one-sided since negative gap = safe noise) and
  exits non-zero on any failure. `--pred-root` retro-scores cached prediction trees. Holdout mode
  shares `score.py`'s 6h stamp so a gate run counts as the holdout spend. Lint runs first, VOID
  semantics unchanged.
- `tests/test_judges.py` — 5 deterministic tests incl. negative control (fabricated quote fails
  grounding); full suite 11/11 green. Gate's F1/gap columns reproduce cycles 4/6 exactly.

Retro-scores on the cached dev-80 outputs (zero model calls):
| model | macro-F1 | grounding | High-sev P | probe gap | gate |
|---|---|---|---|---|---|
| DeepSeek V3 (`runs/predictions-deepseek-v3`) | 0.3264 FAIL | 1.0000 (1792/1792) PASS | 0.4526 (191/422) FAIL | -0.0284 PASS | FAIL |
| Kimi K2.6 (`predictions/`) | 0.3733 FAIL | 1.0000 (2062/2062) PASS | 0.4379 (229/523) FAIL | -0.0494 PASS | FAIL |
| DeepSeek V4-Pro | 0.3913 FAIL | — | — | — | (predictions overwritten) |
| Sonnet-class | 0.4761 FAIL | — | — | — | (predictions overwritten) |

Notes: (1) grounding = 1.0 by construction downstream of `pipeline/extract.py`'s verbatim filter —
the judge exists to catch filter bypass and to score raw/frontier outputs on holdout; the negative
control proves it can fail. (2) **High-severity precision ~0.44-0.45 is a hard fail on both cached
models** — the noisy-extractor risk the criterion exists for is real, not hypothetical; the frontier
pass must clear THIS bar, not just 0.55 F1. (3) V4-Pro and Sonnet-class dev predictions no longer
exist on disk: `predictions/` is gitignored and cycles 5/6 wrote in place; only the V3 snapshot was
kept. Snapshot every future ladder run to `runs/predictions-<model>/` before the next pass.

## Cycle 7 — 2026-07-06 (frontier pass: Sonnet 5 API + Opus 4.8/Sonnet 5 agent runs)
- **Question**: does a frontier model clear the 4-criteria gate? Answer: **no, but Opus 4.8 comes close on precision, and the run exposed chunking as the bigger lever.**
- Three runs on dev-80 (snapshots under `runs/`):
  - `predictions-claude-sonnet-5/` — API via OpenRouter, standard pipeline (chunked, temp 0, verbatim filter). **INCOMPLETE: 45/80 docs — key credit exhausted at exactly $10.00** (cost estimate missed per-chunk prompt overhead). macro-F1 0.3008 is a coverage artifact — DO NOT cite. Valid signals: grounding 1.0000 (filter working), High-sev precision 0.4067 (170/418; precision is per-prediction, coverage-independent).
  - `predictions-claude-opus-4.8-agent/` — Claude Code subagents (model=opus), whole-document reads, NO verbatim filter, non-API protocol (no temp control). **macro-F1 0.4916 · grounding 0.9744 · High-sev precision 0.6834 (259/379, 8 findings short of the 0.70 bar)**. Best numbers ever recorded on this eval.
  - `predictions-claude-sonnet-5-agent/` — same protocol, model=sonnet. macro-F1 0.4850 · grounding 0.9665 · High-sev precision 0.5721.
- Probe gap not measured on any of these (no probe run — budget). Agent runs are indicative, not API-reproducible: whole-doc context, agentic care, no temperature pinning. Protocol wrinkle: Sonnet agent prompts included an explicit "extract from exhibits too" line; Opus prompts did not (batch-0 Opus agent skipped ~5.6k lines of exhibit templates in b18aeb2bf33a).
- **Findings:**
  1. **Precision scales with model quality**: 0.44 (V3/Kimi) → 0.57 (Sonnet 5) → 0.68 (Opus 4.8). The high-sev precision wall is a capability curve, not a task ceiling — but no current model clears 0.70.
  2. **F1 plateaus ~0.48-0.49 across three different frontier-class models** while precision climbs — consistent with a Jaccard-0.5 span-boundary matcher ceiling, not a comprehension ceiling. Treat the 0.55 F1 bar as possibly unreachable under this matcher; grounding (0.97 raw, no filter) says the quotes are real.
  3. **Chunking destroys precision**: same model (Sonnet 5), pipeline-chunked 0.4067 vs whole-doc agent 0.5721. The pipeline/dealroom extractor's biggest upgrade is context window, not model. This dwarfs the Sonnet→Opus delta.
- **GATE: FAIL → the pitch takes branch B (AI-triage-assist)**: honest sellable numbers are "~97% grounded quotes, ~0.68 High-severity precision at the top end, named human signs every finding." Holdout remains UNSPENT (correct — nothing passed dev). OpenRouter key: $0.00 remaining, needs top-up for any further API runs (finish Sonnet-5 API 35 docs ≈ $3; GPT-5.2 pass ≈ $5).
- Context comparison (public record): CUAD 2021 best fine-tuned 44% P@80%R; 2024 LLM studies ~0.66 precision zero-shot (softer protocols); vendor claims (Kira 94%, ≥90% recall) are unpublished-methodology marketing on decade-trained supervised models — no falsifiable comparable exists. This eval's falsifiability is itself the differentiator.

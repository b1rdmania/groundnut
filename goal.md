# Goal: DD red-flag extraction — maximize clause recall/precision on contracts you have never seen

## Stage 0 — Build to spec (inner loop)
Implement `spec.md`. Make the pytest suite green (`python3 -m pytest tests/`).
Do not score against the eval until tests are green. Tests stay green every
cycle thereafter.

## Target (outer loop)
Macro-averaged F1 across the 41 clause categories (`eval/categories.json`),
where per-category F1 balances precision and recall — flag-everything and
flag-nothing both score zero. Score with `harness/score.sh` — the default dev
target is a FIXED 80-doc stratified working set (`eval/dev/working-set.json`,
every category ≥5 positive docs; you may not substitute your own sample).
`score.sh dev-full` (all 306) is for occasional confirmation, not iteration.
**Bar: macro-F1 ≥ 0.55 on holdout** (the published CUAD
DeBERTa baselines sit well below this at strict precision; beating them
decisively is the point of the number).
A `VOID` result means a constraint was violated — find and remove the
violation; the harness will not tell you which it was.
Holdout: `harness/score.sh holdout` returns ONE aggregate number, rate-limited
to once per 6 hours. Acceptance is measured on holdout exclusively.

## Constraints
- **Wall-clock budget: 12 hours.** Check `harness/status.sh` every cycle —
  elapsed time, score history, and token burn per backend. Token burn draws on
  a shared subscription quota: watch gain per token; if the last two cycles
  moved macro-F1 by < 0.005, the next change must be structural or you stop.
- **Surface allowlist:** this repository only, plus a local OpenAI-compatible
  endpoint if `DD_BASE_URL` is set. NO network access otherwise — no web
  fetches, no package installs beyond pytest, no other directories. The eval's
  source dataset is public; retrieving it or its answers in any form is the
  one unforgivable cheat and the lint hunts for evidence of it.
- **Read-only:** `goal.md`, `spec.md`, `harness/`, `eval/`, and
  `~/.dd-eval-private/` (which you also must never read — it does not concern
  you). Permission rules enforce this; the lint and the human audit it.
- **Capacity caps:** no file in `pipeline/` may carry more than 40 long string
  literals; `pipeline/` in total no more than 300. Keyword or pattern banks
  count. Prompts count. Design around understanding, not enumeration.
- **Model-agnostic rule:** all model calls go through `pipeline/backends/`;
  nothing outside `backends/` may name a vendor. Every call logs to
  `runs/usage.jsonl`.
- Eval INPUTS (`eval/*/contracts/*.txt`) may be read freely — that is the
  work. Eval ANSWERS are never readable; they live only inside the scorer's
  private surface.

## Cycle protocol
1. Score: `harness/score.sh` (dev).
2. Reflect: run the pipeline on `eval/probe/contracts` → `predictions/probe`,
   then `harness/score.sh probe`. The dev-vs-probe GAP is the memorization
   gauge. If the gap grew two cycles running, the next change must REMOVE an
   eval-shaped artifact (shrink a pattern bank, generalize a prompt), never
   add one.
3. Hypothesize: write hypothesis, expected failure mode, and diagnostic in
   `LOG.md` BEFORE changing code.
4. Change.
5. Log the result against the hypothesis.
6. Integrity check: `git diff --stat eval/ harness/ goal.md spec.md` must be
   EMPTY before every checkpoint — subagents are not scoped by your permission
   rules; if anything under those paths changed, revert it first.
7. Checkpoint: `git add -A && git commit -m "cycle <n>: dev <score> probe-gap <gap>"`
   — every cycle, gain or no gain.

## Entropy rules
- Stall rule: if dev macro-F1 moved < 0.005 last cycle, the next attempt must
  be a structural change (different chunking, different prompt architecture,
  different category grouping, different backend mix) — same-knob-harder is
  banned.
- Exploration quota: every 5 cycles, try one structurally different approach
  even if the current one is still inching up.
- Category triage: `score.sh` prints per-category F1. Spend cycles where the
  F1 mass is, not on the category you find interesting.

## Stop conditions
Bar hit on holdout · 12h wall-clock exhausted · subscription quota exhausted
or gain-per-token flat (< 0.005 macro-F1 per cycle for 3 consecutive cycles) ·
On stop: write a final report in `LOG.md` — best holdout score, per-category
profile, what generalized, what was abandoned, and the recommended
model/backend mix for the production pipeline (the model-agnostic design call
depends on this).

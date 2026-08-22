# Semantic-support admission plan v1

Status: DRAFT, preregistered before any human review row exists. Written
2026-08-22. Becomes binding when `scripts/freeze_support_plan.py` emits the
`groundnut-support-probe-plan/v2` artifact; the artifact must agree with every
number below or this document is wrong and must be amended *before* the probe
runs, never after.

The purpose of this plan is to replace `NOT MEASURED` on the canonical
semantic-support gate with one measured result, pass or fail, that cannot be
tuned after the fact.

## Fixed inputs (already frozen in the review manifest)

| field | value | where |
|---|---|---|
| review manifest sha256 | `06b3f511c0fbbf35cbebc8722ab23fcfa09b98b10dd02dec77e92974ccfeb3e8` | `support-pilot-review.jsonl.manifest.json` |
| source pool sha256 | `f089eb67…fce7b4` | LegalBench-RAG safe pool, 271 docs |
| excluded pool sha256 | `1e474fa2…10e2d7` | 191 holdout docs, never read |
| sampling seed | 991 | |
| target groups | 50 | |
| reserve groups | 25 | manifest order only |
| max context characters | 4096 | |
| lexical overlap band (paraphrase) | 0.20 – 0.80 | |

Cases per group: 4 (`verbatim_supported`, `paraphrase_supported`,
`contradicted`, `present_irrelevant`). Probe N = 200 cases, 50 per kind.
Expected labels: `supported` (×2 kinds), `contradicted`, `insufficient`.

## Human review protocol

Reviewer identity: **TBD** — a named human other than the project owner,
recorded as `human:<id>`. No reviewer is currently assigned; until one is,
the gate stays NOT MEASURED. No agent may write a `*_decision` field.

Per row, three rulings, in this order:

1. **Irrelevance.** Accept only if the present candidate span, read on its own,
   does not answer the target question *at all*. "Partly answers", "answers a
   related question", "could be read as answering" → `ambiguous`. Ambiguous is
   not a negative label; the row leaves the pilot.
2. **Paraphrase.** The agent draft is a proposal. Accept only if (a) a lawyer
   would say it asserts the same obligation as the attested text, no more, no
   less, and (b) it is not a substring of the context. Edit freely; an edited
   paraphrase keeps `model_authored` provenance with `human:andy` as reviewer.
   If it cannot be made to satisfy (a) inside the overlap band, `rejected`.
3. **Contradiction.** The negation-flip proposal is deterministic and often
   clumsy. Accept only if the flipped text, placed where the attested text is,
   would make the source *assert the opposite*. A flip that merely makes the
   sentence meaningless or ambiguous → `rejected`.

Row admission: all three accepted. Any `pending`, `rejected`, or `ambiguous`
drops the row; the next reserve in manifest order replaces it. The reviewer
does not see, and the scripts do not expose, any detector output on any row
before all 50 are admitted.

Stopping rule: review runs to 50 admitted rows or to exhaustion of the 75.
If fewer than 50 admit, the probe is **not built** with a smaller N; the pack
is re-sampled with a new seed declared in plan v2. No partial result is
reported.

A row taking more than 4 minutes is probably `ambiguous`.

## Policies under test

Baseline: `exact_support_baseline` (policies/exact-support-baseline-v1.json,
normalised substring, min_confidence 1.0). On the exploration pack this scored
three-way macro-F1 **0.167** — it can only ever say `supported` on verbatim
rows and `insufficient` elsewhere.

Candidate: **one** detector policy, to be frozen as
`policies/composed-support-candidate-v1.json` before the probe runs. It must be
the *composed* policy — exact check first, then AlignScore-NLI
(entailment / neutral / contradiction preserved) on the residue, Groundnut
abstention on low margin — not the bare detector.

Reason, and this is the point of the plan: the admission rule fails any
candidate whose per-kind accuracy drops below baseline on *any* kind
(`support_admission.py:272`). Baseline is ~1.0 on `verbatim_supported` by
construction. A bare NLI model that misses even one verbatim case fails
admission regardless of its macro-F1. Only a composition that inherits the
exact check can pass. That is the intended behaviour, not a loophole to fix.

No second candidate. If the composed policy fails, the result is FAIL and the
next attempt is plan v2 on a *new* pack. No tuning against these 200 cases.

## Admission rule

| field | value |
|---|---|
| `primary_metric` | `macro_f1` (three-way, over `supported` / `contradicted` / `insufficient`) |
| `minimum_improvement` | **+0.20 absolute** over baseline macro-F1 |
| per-kind regression | any kind with candidate accuracy < baseline accuracy fails (enforced in code, not configurable) |
| completeness | both runs must assess all 200 cases; an abstention is a prediction of `insufficient` and is scored as such |

Why 0.20: exploration (agent-screened, not admissible) put the best complete
candidate at 0.404 vs 0.167, a gap of 0.24. At N=200 with 50 per kind, the
standard error on a single-kind accuracy is ~0.07; a macro-F1 gain under
~0.15 is not distinguishable from noise and a gain of 0.20 is the smallest
that would survive the exploration-to-adjudicated drop we expect (the
exploration negatives were agent-screened and easier). 0.20 is the one number
in this plan that is a judgement rather than a derivation. Argue with it
before freeze, not after.

What a pass means: the composed policy is admitted as the frozen canonical
support signal for the CUAD/LegalBench-RAG domain pack *only*. It does not
transfer to any other domain pack, and it says nothing about truth.

What a fail means: GATES.md moves from `NOT MEASURED` to `FAIL` with the
number, published unchanged, holdout still unspent. Same treatment as the
CUAD extraction gate.

## Holdout

The 191 excluded documents are not read, hashed into any context, or used to
choose the seed, the candidate, or the threshold. Nothing in this plan
authorises touching them. A pass here is a *development* gate; the holdout run
is a separate plan.

## Preconditions from the 22 Aug review (docs/plans/review-2026-08-22.md)

Fix before step 1, none of which reads a review row: gate verifies gold rows
against the loaded probe (A1); reviewer ids must carry `human:` and differ from
the author (A3); build records rejected/ambiguous counts and an attempt number,
and the plan binds `review_manifest_sha256` (A5); canonical runner accepts the
registered composed policy (B2). These are guards on the process, not changes
to the cases or the threshold.

## Execution order (session B)

1. `apply_support_reviews.py` → `support-pilot-reviewed.jsonl`
2. `build_support_probe.py` → `support-pilot-cases.jsonl` (fails closed on any
   pending row; must report exactly 50 groups)
3. Freeze `composed-support-candidate-v1.json`; commit its hash. Note
   `canonical_cli.py:103` rejects every detector except `ExactSupportDetector`
   by class; the composed policy needs a registered adapter before the probe
   runner can execute it. That is engine code, written before any case is
   scored, and it must not read the review rows.
4. `freeze_support_plan.py --key support-admission-v1 --primary-metric macro_f1
   --minimum-improvement 0.20 --baseline-policy exact-support-baseline-v1.json
   --detector-policy composed-support-candidate-v1.json`
5. Run baseline probe, then candidate probe, sequentially, `workers=1`.
6. `python3 -m groundnut.support_gate_cli` → admission artifact.
7. Publish aggregate numbers to GATES.md and docs/SUPPORT.md. Never publish
   case text.

Steps 1–2 and 5–6 are mechanical. Step 3 is the only place a choice is made
after this document, and it is made before any case is scored.

## Amendment rule

This file may be edited until the plan artifact exists. After that, changes
go in `support-admission-plan-v2.md` with a new pack. The artifact's
`frozen_at` is the cut.

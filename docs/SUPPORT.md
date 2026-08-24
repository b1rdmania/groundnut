# Semantic support contract

Status: active experiment and admission contract. The exact baseline is the
only detector admitted to the current product path; the learned gate remains
**NOT MEASURED**.

Groundnut distinguishes mechanical evidence from semantic support. Source
resolution and excerpt anchoring run first and remain immutable. An optional
support detector produces a separate assessment under a frozen policy.

## Outcomes

- `supported` — the detector judged that the supplied source supports the
  claim under the recorded question/task context.
- `contradicted` — the detector found source evidence in conflict with the
  claim.
- `insufficient` — the available evidence or detector confidence did not
  establish support or contradiction.
- `source_unavailable` — acquisition failed or the resolved source identity
  changed; the detector is not called.
- `not_assessed` — no external source exists, the detector failed, or semantic
  assessment was deliberately not performed.

These outcomes do not mean true or false. They describe the relationship
between one claim and the exact source bytes supplied to one recorded checker.

## Frozen policy

Every assessment records:

- adapter, model, immutable model revision, package, and package version;
- the detector identity hash;
- policy key, version, freeze time, threshold, and policy hash;
- source hash and a host-independent hash of source, claim, and question;
- normalized decision, adverse spans, and an optional raw-output hash.

A moving model reference such as `main` or `latest` is rejected. An unscored
decision is accepted only when the frozen policy explicitly has no confidence
threshold. Detector spans must match the claim text at their reported offsets.
Adapter errors yield `not_assessed`; they never erase a mechanical result.

`policies/exact-support-baseline-v1.json` pins the deterministic normalized-
substring baseline. Absence from the source is `insufficient`, never
`contradicted`.

`check_claims` is the canonical batch surface. It resolves each claim against
the supplied `SourceResolution`, preserves the mechanical `VerifiedClaim`, runs
the frozen detector only when a source is available, and emits an order-stable
`groundnut-claim-check-report/v1`. Completeness and status/mechanical metrics
are derived from the immutable rows. The report is schema-tagged and self-
hashed, so it can be added to `groundnut-run-manifest/v1` as an artifact.

## Valid transfer probe

Every probe group contains four cases derived from one source clause and one
question:

| Kind | Claim occurs verbatim? | Expected support |
|---|---:|---|
| `verbatim_supported` | yes | `supported` |
| `paraphrase_supported` | no | `supported` |
| `contradicted` | no | `contradicted` |
| `present_irrelevant` | yes, elsewhere | `insufficient` |

This layout makes substring presence useless as a perfect classifier: each
side contains one present and one absent claim. `SupportProbe` additionally
requires every group member to share the source ID/hash, original offsets and
text, and question. Both present claims carry source offsets. One identical
group window is derived from their combined offset envelope, never by searching
for derived text, and construction fails if both do not fit.

Case files are JSONL using `groundnut-support-case/v3`. Every row carries
`attested`, `adjudicated`, `derived`, `authored`, or `model_authored`
provenance, including its source record, construction method, parents,
reviewers, and disclosure.
Model-authored rows cannot enter a probe without a recorded human reviewer;
contradictions require derived provenance; and supported verbatim rows require
attestation. Present-but-irrelevant rows require adjudicated provenance and a
recorded human reviewer; CUAD/LegalBench-RAG absence is never accepted as a
negative annotation. Paraphrase token overlap is recorded deterministically so
a generated positive class cannot be made trivially easy without showing it.

The loader verifies schema, group completeness, source hashes, original
offsets, presence/absence conditions, unique IDs, and a stable
order-independent manifest hash. Gold rows feed the one-to-one `score_support`
scorer, where missing predictions count as wrong and extra predictions are
rejected.

## Benchmark construction and review

`scripts/import_legalbenchrag.py` imports the upstream LegalBench-RAG shape
(`tests[].query`, `tests[].snippets[].file_path`, and character `span`) into
`groundnut-support-seed/v1`. It checks every offset against the actual source
text and excludes any document whose text SHA-256 occurs in Groundnut's holdout
manifest. The resulting source-pool and excluded-pool hashes become inputs to
the frozen probe plan.

Imported spans remain seeds, not automatic four-cell gold. The upstream span
link is expert-derived while some query wording is generated, and that
distinction stays in provenance. A different-query span from the same document
is a useful `present_irrelevant` candidate, but it requires adjudication because
one legal clause can answer more than one question.

`scripts/sample_irrelevant_candidates.py` constructs a fixed review batch from
the imported seeds. It removes identical and overlapping cross-query spans,
uses a deterministic sampling seed, and by default selects at most one pair per
source document. `--max-span-envelope` ensures both present spans can occur in
the detector's real input window. Its output schema is explicitly a candidate
batch, not gold.
Only a human ruling that the present span does not answer the target query can
promote a row to `present_irrelevant`, at which point its case provenance is
`adjudicated`, not `attested`.

`groundnut-evidence-annotation/v1` is the workbench interchange. It preserves
source hashes and offsets, creator kind (`human`, `dataset`, `analyzer`, or
`agent`), review state, reviewers, and relationships. This maps cleanly onto
OpenContracts' document/annotation/relationship model without requiring the
Groundnut engine to run its Django stack. Only accepted annotations can become
attested support seeds, and accepted non-human annotations require a human
reviewer. See [`ANNOTATION.md`](./ANNOTATION.md).

The canonical pilot workflow is executable but stops at the human boundary:

1. `scripts/prepare_support_pilot.py` freezes 50 target groups plus 25 ordered
   reserves, emits immutable JSONL, and creates a TSV worksheet containing the
   exact review context and deterministic negation proposal.
2. `scripts/render_support_review.py` optionally turns that private batch into
   a self-contained offline reviewer which downloads the same TSV format. An
   optional `--suggestions` JSONL sidecar may prefill visibly agent-authored
   drafts; it cannot alter the frozen rows or create a human decision.
3. A human rules irrelevance, authors or reviews the paraphrase, and reviews
   the contradiction. Nothing pending is treated as accepted.
4. `scripts/apply_support_reviews.py` rejects changed source text, questions,
   proposals, missing rows, duplicate rows, and reviewer-free acceptances.
5. `scripts/build_support_probe.py` promotes the first 50 fully accepted rows
   in the preregistered order and enforces the frozen lexical-overlap band.
6. `scripts/freeze_support_plan.py` binds the completed probe, its build
   receipt, and the review manifest to exact policy hashes before any learned
   run. The canonical path executes only detectors listed in
   `groundnut/admitted_detectors.py`; a passing admission artifact is the
   precondition for adding one.

The offline reviewer shows the 50 target rows first and hides reserves by
default. Applying a suggestion copies its agent identity into paraphrase
authorship while requiring a separate human reviewer ID. Human notes remain
independent. Drafts outside the frozen lexical-overlap band or found verbatim
in context become ambiguous rather than accepted.

When human adjudication is not available, `scripts/screen_support_suggestions.py`
provides a deliberately weaker development route. It checks that agent
suggestions exactly cover the preregistered target rows, excludes every
rejected or ambiguous group, and emits a self-hashed screen with
`qualification: exploratory_only` and `eligible_for_admission: false`. This is
useful for debugging adapters and estimating whether a learned detector is
worth further work. It cannot create `adjudicated` provenance, promote cases to
gold, qualify a detector, or change the canonical gate from `NOT MEASURED`.

`run_support_bakeoff` then runs every frozen policy over those identical cases,
writes complete run artifacts, recomputes each score, and produces one
self-hashed admission decision per candidate. External packages remain
benchmark surfaces; the bake-off does not adopt them into Groundnut.

`run_support_probe` executes any frozen detector over those cases only under a
`groundnut-support-probe-plan/v3`. The plan freezes N, sampling seed, the exact
probe hash, source and exclusion pool hashes, context size, baseline and
detector policy keys plus their exact configuration hashes, primary metric,
minimum meaningful improvement, and permitted paraphrase-overlap band before a
learned detector runs. The runner derives
every context from the original offsets, records a hash and length for each
window, binds detector and policy identity to every assessment, computes the
one-to-one score, and emits a self-hashed `groundnut-support-probe-run/v3`
artifact containing the gold rows required to recompute its declared score.
Mixed policies, mismatched context hashes, source tampering, missing
case IDs, duplicate IDs, post-hoc sample-size changes, and unregistered policies
fail before a result can be accepted.

`python3 -m groundnut.support_gate_cli` is the offline admission consumer. It
loads the frozen plan plus baseline and candidate run artifacts, verifies every
self-hash and shared identity, recomputes both scores from gold and assessment
rows, enforces the preregistered improvement, and rejects regression on any
material case kind. Exit codes are 0 for pass, 1 for a valid non-pass, and 2 for
invalid or tampered input. Its result is a self-hashed
`groundnut-support-admission/v1` artifact.

## Adapter admission

Groundnut includes benchmark-only adapters for AlignScore, LettuceDetect, and
MiniCheck, but no model is an adopted dependency or quality claim. Imports load
no model runtime and tests inject fakes without network access.

The AlignScore adapter requires a pinned local checkpoint and pinned local
RoBERTa backbone metadata. Its NLI mode preserves entailment, neutral, and
contradiction instead of collapsing them into the upstream convenience score.
Its separately identified QA mode combines the question and answer and remains
binary. The two modes have different detector identities and cannot be silently
substituted.

The Lettuce adapter requires a pinned local model directory for real loading;
it will not resolve a moving Hugging Face reference. A clean span result is an
unscored `supported` decision, an explicitly typed contradiction maps to
`contradicted`, and every other unsupported span maps to `insufficient`.

The MiniCheck adapter requires an already-loaded, revision-pinned scorer because
the package constructor does not expose an immutable model revision. Its binary
negative maps to `insufficient`, never `contradicted`. Code/package and model/
dataset licences must be recorded separately for both adapters.

A learned detector remains an optional research dependency until it:

1. runs over the same frozen cases and identical context windows as every
   baseline;
2. records its code licence and each model/dataset licence separately;
3. beats the exact and lexical baselines on macro-F1 and on every material
   failure kind, not only aggregate accuracy;
4. has its decision mapping and threshold frozen before holdout scoring;
5. remains reproducible from cached outputs without network or model calls on
   the deterministic gate path.

The first domain set should emphasize supported paraphrases, negation,
number/unit changes, attribution errors, present-but-irrelevant excerpts, and
inaccessible sources. No private holdout material is used to construct it.

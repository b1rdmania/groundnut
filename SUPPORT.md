# Semantic support contract

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
text, and question. Context windows are computed from that shared original
span, never by searching for a derived claim that may be absent.

Case files are JSONL using `groundnut-support-case/v1`. The loader verifies
schema, group completeness, source hashes, original offsets, presence/absence
conditions, unique IDs, and a stable order-independent manifest hash. Gold rows
feed the one-to-one `score_support` scorer, where missing predictions count as
wrong and extra predictions are rejected.

## Adapter admission

Groundnut includes benchmark-only adapters for LettuceDetect and MiniCheck, but
neither model is an adopted dependency or quality claim. Imports load no model
runtime and tests inject fakes without network access.

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

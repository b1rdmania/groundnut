# Canonicalization map

Status: transition record, not the current product roadmap. The IC research
loop is now Groundnut's product; this document records how reusable contracts
moved out of the original CUAD compatibility path.

The migration is additive: compatibility behaviour remains stable while the IC
loop adopts the canonical checking and ledger contracts deliberately.

## 0.2.0a2 evidence-boundary hardening

This build gives the post-KISS-review behavior a distinct package identity.
Fuzzy similarity is diagnostic-only; only byte-exact and named mechanical
normalisation establish excerpt presence. Claim ledger v5 and verification
metrics v6 expose that distinction. Snapshot and acquisition v3 preserve a
sanitized final-response URI and bind canonical source identities across
sessions while retaining historical snapshot replay.

The release also repairs realistic PDF-worker input handling, nested HTML
containers, declared character sets, hollow evidence windows, artifact-location
admission, support-baseline integrity, strict receipt JSON, canonical URI drift,
and the deprecated 6to4 address-policy gap. Consumers remain pinned until they
pass their own replay and integration suites against this release.

## 0.2.0a1 acquisition and locator hardening

The 0.2 alpha boundary builds on 0.1.0a15 rather than replacing its
snapshot-qualification contract. The default live transport admits only public
HTTP(S) destinations, revalidates redirects, and binds each socket to an
admitted address while preserving the original HTTP and TLS hostname. Encoded,
decoded and extracted content are bounded. PDF extraction runs in a separate
resource-limited worker. Injected HTTP or DNS transports now require the
explicit privileged opt-in `allow_injected_transport=True`.

Bare locators without a public URI remain in the claim population as
`unresolvable_source`; they count as declared evidence but not as resolvable or
accessible evidence. Artifact segmenter v4 and ledger segmenter v7 carry that
classification. The combined claim-verification serialization is v4 and
verification metrics are v5, avoiding a collision with a15's v3/v4 contracts.

This release remains security work in progress. These controls are not a
comprehensive security review or approval.

## 0.1.0a15 snapshot-qualification migration

Issue #40 replaces the mechanically misleading quotation method `exact` with
`byte_exact` for raw substring presence and `normalised` for presence after
named transformations. Verification metrics v4 publishes byte-exact,
normalised and fuzzy populations separately; the top-level `found`,
`ambiguous`, and `not_found` outcomes remain stable. Neither presence method
establishes semantic support or truth; issue #18 remains the separate admission
project.

Capture declaration v3 replaces the global retain list with exact-host query
policies and makes policy application visible in v3 receipts without query
values or credential-shaped names. V2 declarations and receipts continue to
replay without changing their bytes or hashes. Consumers should replace custom
URI joins with `resolve_snapshot()`, which is replay-only and returns typed
failures for missing, corrupt, HTTP-failed, empty, incomplete, and hollow
observations.

After a Groundnut release is pinned and the sealed Phase 1/2 qualification
passes (215 indexed citations; 205 byte-exact excerpts; nine locator-only; one
reference-only; zero unusable), the IC pipeline may remove its temporary hollow
capture scanner, direct substring checks, evidence-resolution adapter, and
consumer-specific snapshot joins. Those pipeline changes are intentionally not
part of this Groundnut change.

## Landed in Groundnut

- Versioned domain packs with category and document-type taxonomies.
- Separate playbook and evidence-manifest hashes.
- Explicit evidence maturity; shipped packs are currently experimental.
- Checklist-driven extraction with exact source anchors and source hashes.
- Fail-closed per-segment coverage (`risk_found`, `checked_clear`,
  `incomplete`).
- Local/HTTP source resolvers with honest failure states and verified snapshots.
- Frozen-policy adversarial arena with distinct-family/session rulings,
  withheld disagreement, and fail-closed incomplete work.
- Offline arena consumer with CI-safe exit semantics; hosts decide what to do
  with its immutable report.
- Raw corpus-manifest hash enforcement.
- Frozen semantic-support contracts with exact detector identity, immutable
  mechanical verification, and one-to-one development scoring.
- Paired four-cell transfer probes whose shared source origin and crossed
  substring labels prevent the invalid detector comparison from recurring.
- Canonical run manifests binding engine, playbook, evidence, source/snapshot,
  policy, runtime-component, and output-artifact hashes.
- Typed analytical provenance for external evidence, company assertions,
  analyst calculations, analyst inferences, recommendations, and open
  questions, kept independent from support and authority.
- Hash-bound calculation formulas, unique named inputs, and checked
  source-claim references, without upgrading declared arithmetic to support.
- Denominator-safe mechanical metric envelopes with byte-exact and normalised
  found populations kept separate from fuzzy ambiguity diagnostics.
- Explicit segmenter identity bound into artifact extraction and canonical run
  manifests.
- Generic render-bound evidence parity with explicit excluded regions,
  renderer/configuration identity, and a self-hashed fail-closed receipt.
- End-to-end batch claim checking with derived completeness, mixed-state
  reporting, and manifest-ready self-hashed output.
- Offline-testable LettuceDetect and MiniCheck benchmark adapters with pinned
  configuration identity and conservative non-truth mappings.
- Reproducible paired-probe execution with per-context hashes, one-to-one
  scoring, strict identity checks, and a self-hashed benchmark artifact.
- Provenance-rich support cases, contamination-safe LegalBench-RAG seed
  import, and an OpenContracts-compatible annotation/review interchange.
- Frozen support-probe preregistration binding N, the exact probe, sample
  pools, context, policies, metric, meaningful difference, and paraphrase-
  overlap bounds.

The reusable contracts remain where they support the IC loop or a measured
candidate for it. Persistence and operator/review surfaces are justified only
when they close a demonstrated product or benchmark gap. Identity, credential
use, publication and sign-off remain explicit host or human authority. Tests
are offline by contract and acquisition adapters are always invoked explicitly.

## Product-led priority

1. Run fresh decks through the IC loop and fix failures in citation checking,
   snapshot replay, segmentation and the claim ledger.
2. Tighten semantic support: benchmark optional support
   detectors on paraphrase, contradiction/negation, numeric, attribution, and
   irrelevant-evidence cases without weakening retrieval provenance or
   fail-closed coverage.
3. Establish labelled development sets and frozen bars for each exact domain
   pack before making quality claims.
4. Test segmentation and merge behaviour under a controlled protocol,
   including the largest documents.
5. Make arena and verification artifacts composable without allowing an
   absent attack, inaccessible source, or unassessed quotation to imply truth.
6. Keep the compatibility pipeline stable while the IC path earns its own gates.

Groundnut can own database models, audit-chain persistence, and review UI when
they are part of the canonical checking system. It does not silently exercise
authentication, credentials, publication, or sign-off authority.

## Current product: IC research

The research pipeline calls `groundnut.ic_loop` after the thesis writer. The
current output is a replayable run and claim ledger; semantic support,
relevance, navigation and decision machinery enter only after their own frozen
conditions pass.

Groundnut does not absorb private company material, credentials, audience
rules, publication authority or investment decisions. Those remain in the
host workflow even though the IC loop drives Groundnut's product roadmap.

## Deferred consumers

Existing product deployments, a future v2, and an operating-system port are
possible consumers—not current milestones. Any future adapter must pass the
generic semantic contract in `PARITY.md` before it replaces a host path, but
building such an adapter is deliberately not on the critical path.

## Evaluation work before qualification

The legacy four-criterion CUAD gate is retained unchanged as the compatibility
extractor gate, not Groundnut's product acceptance bar. Its current failure is
still published. The canonical semantic-support gate is explicitly
`NOT MEASURED` until the adjudicated probe is frozen; this is a documented gate
split, not a quiet metric replacement. See `../GATES.md`.

- Fix prediction/gold scoring to enforce one-to-one matches under a reviewed
  harness change.
- Derive any new matcher and threshold before re-scoring.
- Run a controlled chunking comparison and largest-document merge test.
- Build labelled sets for the exact 18-category M&A, procurement, and trust
  packs. The existing 41-category contract evaluation belongs only to its own
  legacy playbook.
- Keep holdout unspent until a frozen development rule passes.

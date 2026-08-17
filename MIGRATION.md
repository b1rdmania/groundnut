# Canonicalization map

Groundnut is becoming the reusable engine rather than the place one deployment
copied extraction code from. The migration is additive: hosts remain unchanged
until they deliberately adopt a stable Groundnut contract.

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

The widened method-layer scope is a dated decision in `ARCHITECTURE.md`. It
does not move the stop line: no auth, application persistence, credential
custody, UI, deployment policy, or sign-off authority belongs here. Tests are
offline by contract and acquisition adapters are always invoked explicitly.

## Canonical-engine priority

1. Tighten the anti-hallucination contract: benchmark optional support
   detectors on paraphrase, contradiction/negation, numeric, attribution, and
   irrelevant-evidence cases without weakening retrieval provenance or
   fail-closed coverage.
2. Establish labelled development sets and frozen bars for each exact domain
   pack before making quality claims.
3. Test segmentation and merge behaviour under a controlled protocol,
   including the largest documents.
4. Make arena and verification artifacts composable without allowing an
   absent attack, inaccessible source, or unassessed quotation to imply truth.
5. Keep the compatibility pipeline stable while the canonical API earns its
   own gate.

Authentication, database models, audit-chain persistence, sign-off workflow,
and UI remain host concerns. Groundnut may produce hashable artifacts for those
systems to store and sign, but it does not decide who is authorised to do so.

## Future proving ground: IC research

Groundnut will be the basis for renewed IC work once its own contracts and
measurements are tight. The reusable primitives already landed here; the next
IC-facing work is to add domain task emitters and a complete run manifest while
keeping report-specific conclusion heuristics outside the engine until they
generalise.

The IC repository remains read-only and paused. Groundnut receives reusable
contracts; it does not absorb IC fixtures, private company material, credentials,
or deployment policy.

## Deferred consumers

Existing product deployments, a future v2, an operating-system port, and an
open-source release are possible consumers—not current milestones. Any future
adapter must pass the generic semantic contract in `PARITY.md` before replacing
a host path, but building such an adapter is deliberately not on the critical
path.

## Evaluation work before qualification

- Fix prediction/gold scoring to enforce one-to-one matches under a reviewed
  harness change.
- Derive any new matcher and threshold before re-scoring.
- Run a controlled chunking comparison and largest-document merge test.
- Build labelled sets for the exact 18-category M&A, procurement, and trust
  packs. The existing 41-category contract evaluation belongs only to its own
  legacy playbook.
- Keep holdout unspent until a frozen development rule passes.

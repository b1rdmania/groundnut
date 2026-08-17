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
- Raw corpus-manifest hash enforcement.

## Next extraction from the deployment

1. Move document-type classification behind the `DomainPack` contract.
2. Move checklist-agnostic key-property extraction and category batching.
3. Extract deterministic schedule, coverage, and report payload builders as
   pure functions over Groundnut result types.
4. Define a host gateway protocol for model invocation, retries, usage, and
   privilege decisions without importing application sessions or users.
5. Replace the deployment's copied diligence modules with an adapter over the
   released Groundnut package; pin output parity before deleting either path.

Authentication, database models, audit-chain persistence, sign-off workflow,
and UI remain host concerns. Groundnut may produce hashable artifacts for those
systems to store and sign, but it does not decide who is authorised to do so.

## Next extraction from IC research

1. Add claim/citation result types and keep anchor presence separate from claim
   support.
2. Add snapshot-backed verification adapters and numeric-preserving fuzzy
   matching.
3. Add domain task emitters for the arena. Report-specific conclusion
   heuristics remain an IC adapter until demonstrated elsewhere.
4. Record engine, policy, playbook, input, and snapshot hashes in one run
   manifest.

The IC repository remains read-only and paused. Groundnut receives reusable
contracts; it does not absorb IC fixtures, private company material, credentials,
or deployment policy.

## Evaluation work before qualification

- Fix prediction/gold scoring to enforce one-to-one matches under a reviewed
  harness change.
- Derive any new matcher and threshold before re-scoring.
- Run a controlled chunking comparison and largest-document merge test.
- Build labelled sets for the exact 18-category M&A, procurement, and trust
  packs. The existing 41-category contract evaluation belongs only to its own
  legacy playbook.
- Keep holdout unspent until a frozen development rule passes.

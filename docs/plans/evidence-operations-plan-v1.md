# Evidence operations plan: issues 20–22

**Decision date:** 25 August 2026  
**Order:** #20 evidence windows → #22 equivalence → #21 read-time capture

**Shipped:** #20 in `v0.1.0a5`, #22 in `v0.1.0a6`, and #21 in
`v0.1.0a7` (`2611451`). The a8 hardening prevents transformed connector secrets
and exception detail from escaping the capture boundary. The a9 contract makes
query retention default-deny and adds correlatable redacted diagnostics. The
pipeline declaration moves with each invoked capture-contract release.

## Outcome

Groundnut must preserve the exact evidence a research run was able to inspect,
say when that evidence was incomplete, and prove that offline replay reaches
the same evidence judgments. Only after that contract is executable should
pipeline connectors produce snapshots at read time.

This plan deliberately adds no generic connector framework, browser archive or
semantic referee. The first supported producer set is HTTP HTML plus one
non-HTML class. Every stage ends in a machine-readable receipt or deterministic
fixture, not a prose-only assertion.

## Dependency and release rule

```text
#20 snapshot/window v2
        |
        v
#22 equivalence receipt + offline replay proof
        |
        v
#21 declared read-time producers
```

#20 changes the snapshot and assessment contracts that #22 compares. #22 then
becomes the acceptance oracle for #21. Work may be prototyped in parallel, but
it merges in this order. A release cannot claim read-time replay safety until
all three acceptance receipts pass.

## Work package 1 — #20 evidence-window completeness

Extend `ResolvedSource`, successful source snapshots and acquisition records
with an explicit evidence-window object:

- original byte and character length when knowable;
- captured byte and character length;
- truncation state: `complete`, `truncated`, or `unknown`;
- extraction method and its version/configuration identity;
- hash of the exact normalized text searched by verification.

Snapshot v2 is additive and replay must still read v1 snapshots, treating
their completeness as `unknown`. Verification gains
`evidence_window_incomplete`; it must not report `excerpt_not_found` when the
record says the searchable window was truncated or is unknown in a way that
could hide the excerpt. Ledgers and IC JSON surfaces carry the distinction.

Acceptance fixtures place the same target excerpt before and after a fixed
capture boundary. Live and replay classifications must match, and the replayed
window hash must equal the live snapshot's window hash. Tests belong primarily
in `tests/test_sources.py`, `tests/test_verification.py`, `tests/test_runner.py`
and `tests/test_ledger.py`.

Stop condition: do not infer an original length when a transport or extractor
cannot provide one. Record `unknown`; never turn absence of metadata into a
claim of completeness.

## Work package 2 — #22 live/replay equivalence

Add a comparison command that consumes one live canonical run and one replay
run and emits `groundnut-live-replay-equivalence/v1`. It compares:

- claim IDs and normalized claim identities;
- source identities and successful/failure state;
- snapshot and evidence-window hashes;
- anchoring and support assessments;
- policy/profile/component identities that can affect those assessments.

It explicitly excludes retrieval timestamps, acquisition mode, live-attempt
flags and other declared acquisition metadata. A second replay with the same
inputs must be byte-identical after canonical serialization.

The acceptance test supplies a resolver that raises if invoked, runs replay
with network access unavailable, and records zero resolver calls. A comparison
receipt that omits either the compared-field set or excluded-field set is
invalid. Expected nondeterminism is listed in the receipt schema and docs,
never silently ignored.

Stop condition: do not weaken equivalence to make a changing live source pass.
That is evidence drift and should be visible; determinism is the replay claim,
not the live-fetch claim.

## Work package 3 — #21 read-time capture

**Shipped in a7.** The producer declaration, HTML/PDF connector fixtures,
first-read preservation, explicit media/access failures, credential-shaped URI
rejection and sentinel absence test are in place. Pipeline integration is
merged. A real unrelated-deck live/replay/replay receipt remains operational
validation and must not be inferred from the sanitized fixtures.

Define one narrow producer envelope that pipeline connectors can write using
the same snapshot v2 contract Groundnut consumes. Connector names, allowed
media classes and capture intent are declared in `run-config.json` before
dispatch. The pipeline integration pins the exact Groundnut revision and
records the policy/profile and connector configuration hashes in its manifest.

The first integrations cover HTTP HTML and one non-HTML class (prefer PDF
because it is already material to the IC path). They retain normalized content,
safe retrieval metadata and explicit failure states. Credentials, cookies,
authorization values and private response headers are forbidden from canonical
artifacts and are tested with sentinels.

Producer conformance is demonstrated by feeding its snapshots directly into
the replay-only resolver and passing the #22 receipt. Unsupported media,
paywalls and extraction failures remain named failures. A later fetch must not
overwrite an earlier read-time snapshot under the same identity.

Stop condition: do not add adapters for every research tool. Add the next
connector only when a real IC run needs it and can supply a sanitized fixture.

## Operating sequence

1. Freeze snapshot/window v2 schemas and migration behavior; implement #20.
2. Run the boundary fixtures and publish no result until live/replay agree.
3. Freeze and implement the #22 comparison receipt; prove replay uses no live
   resolver and replay two is byte-identical.
4. Update the pipeline run-config contract and its skill instructions for
   declared capture producers. **Complete in pipeline `a25bea1`.**
5. Implement HTML and PDF producer fixtures; scan canonical artifacts for
   credential/header sentinels. **Complete in a7.**
6. Run one private IC report live, replay-only, then replay-only again. **Still
   pending a real unrelated deck.** Preserve
   private rows outside this repository and publish only aggregate hashes and
   the comparison outcome.
7. Tag the tested Groundnut revision, pin that immutable revision in the
   pipeline, and close #20, #22 and #21 in dependency order. **Complete for the
   implementation issues; the step 6 operational receipt is still pending.**

## Roadmap judgment

The current roadmap is largely correct in substance. Full-artifact extraction,
evidence-window honesty, capture-at-read-time, replay equivalence and measured
semantic support are the right capability layers for Groundnut's role as the
shared evidence engine.

Two changes are required:

1. Reorder #20–#22 as this plan specifies. The current issue numbering suggests
   producers before the equivalence oracle, which is operationally backwards.
2. Treat #19 as a measured supported-syntax admission, not a general extraction
   accuracy claim. Expand it through banked real-report fixtures, rather than a
   speculative parser framework.

After #19 closes, #20–#22 are the reliability spine and should precede #18.
Semantic support remains valid roadmap work, but it cannot compensate for an
incomplete evidence window or an unreplayable source. Presentation work and
additional connectors stay consumer-led and should not enlarge the engine until
the current IC path demonstrates the need.

As of a7, #18 is the only open Groundnut roadmap issue. Its position remains
correct, but the immediate next operation is step 6 on a genuinely unrelated
deck. A hard stop on an incomplete window is an expected result of that run,
not permission to weaken the gate; it routes to source operations.

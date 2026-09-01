# Live-to-replay evidence equivalence

**Frozen:** 31 August 2026

**Receipt:** `groundnut-live-replay-equivalence/v2`

**Projection:** `groundnut-live-replay-evidence-projection/v2`

A live run and its replay are not expected to be byte-identical. Acquisition
mode, strategy and live-attempt state legitimately differ. Groundnut instead
compares an evidence projection, then requires a second replay to be
byte-identical to the first.

## Compared projection

The v2 projection compares these fields exactly:

- the complete artifact account, including claim IDs, normalized claim data,
  artifact/profile hashes and segmenter identity;
- source identity, success/failure state, snapshot hash, normalized source
  hash, final-response URI and the complete evidence-window identity for every
  acquisition;
- the complete claim-evidence report, including mechanical verification,
  semantic support and authority assessments;
- arena output, when present;
- engine, domain, policy, component and normalized-source identities from the
  run manifest.

The receipt publishes the projection hashes and hash-only differences. It does
not copy private claim or source text into a comparison result.

New writers emit `groundnut-source-acquisition/v3`; successful v3 acquisition
results must contain `final_uri`. The projection reader also accepts historical
`groundnut-source-acquisition/v2` records, where an absent `final_uri` remains
an explicit unknown rather than being invented. Receipt validation accepts the
historical equivalence v1 comparison-field contract as well as v2. Unknown
acquisition or receipt versions fail with an explicit unsupported-schema
diagnostic.

## Declared exclusions

Only acquisition and derived-envelope metadata is excluded:

- request hashes, because live and replay requests declare different modes;
- acquisition `mode`, `strategy` and `live_attempted`;
- run, execution and manifest hashes derived from those acquisition fields;
- the manifest's canonical-run artifact digest, which binds the deliberately
  different full run rather than the evidence projection.

Retrieval timestamps are not independently compared because they live inside
the immutable snapshot bytes. The snapshot hash is compared, so replaying a
different fetch—even with identical normalized text—is evidence drift, not an
allowed timestamp difference.

## Replay assertions

Both replay inputs must declare `replay_only`, `live_attempted: false` and a
snapshot strategy for every cited source. The implementation test supplies a
resolver that raises if called and verifies zero calls. This proves the engine
path, while the receipt records the replay acquisition assertions visible in
the run.

Replay one and replay two must be byte-identical JSON files. Canonically equal
but differently serialized files do not satisfy the deterministic output
claim.

The two replays may—and normally should—use separate output directories. The
IC loop bundles the checked artifact as `input/report.md`, records the snapshot
directory as the logical path `snapshots`, and excludes that runtime location
from `request_sha256`. Absolute operator paths and usernames therefore do not
enter `request.json`, `run.json`, or the equivalence receipt. Moving an
otherwise identical replay bundle must not change its canonical response.

Replay-only fails closed when any cited source lacks a valid stored snapshot.
An empty or partially copied snapshot set is an invalid replay (exit `2`), not
a successful run with worse citation results. A stored failure observation such
as `source_paywalled` remains a valid replay input because the failure itself
was captured; `snapshot_missing` and `snapshot_invalid` are not.

## Command

```bash
python3.12 -m groundnut.equivalence \
  --live live-run.json \
  --replay replay-run.json \
  --replay-second replay-run-2.json \
  --out equivalence.json
```

Exit `0` means evidence-equivalent live/replay projections, two equivalent
replay projections, byte-identical replay files, and valid replay-only
acquisition declarations. Exit `1` means a valid comparison that differs. Exit
`2` means malformed or unsupported inputs.

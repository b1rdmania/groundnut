# Contributing to Groundnut

Groundnut is the evidence-integrity stage in the IC research loop. A
contribution must improve that product path, close a demonstrated canonical
checking gap, or advance a clearly labelled experiment toward its frozen
admission condition. It must not weaken provenance, determinism, fail-closed
behaviour, or the meaning of an existing measurement.

## Before building

1. Describe the gap with a public or synthetic fixture.
2. State the acceptance condition before evaluating the proposed change.
3. Name the lane: current IC product path, canonical core, active experiment,
   or legacy compatibility. Keep credentials, audience rules, publication
   authority and investment decisions in the host workflow.
4. If a metric, matcher, threshold, policy, or schema changes, version and
   document it. Never reuse an old bar under a new measurement silently.

## Development

Groundnut targets Python 3.12. Install the pinned test dependency and run the
offline suite:

```bash
python3.12 -m pip install -r requirements-dev.txt
python3.12 -m pytest -q
```

Tests block socket access. Inject source resolvers and replay model outputs
instead of reaching the live network.

Keep protected corpus text, credentials, private research, and machine-local
paths out of commits. The public repository can contain synthetic fixtures,
code, manifests, hashes, and aggregate measurements.

## Pull requests

Use a short-lived branch. Keep each pull request to one coherent capability or
correction. Complete the contract and disclosure checklist. Then wait for CI.

The compatibility extraction gate, canonical semantic-support gate, and domain
qualification gates are separate. A change to one never silently passes
another.

# Contributing to Groundnut

Groundnut is the canonical evidence engine for AI-assisted work that must show
its sources and uncertainty. Contributions should close a demonstrated engine
gap without weakening provenance, determinism, fail-closed behaviour, or the
meaning of an existing measurement.

## Before building

1. Describe the gap with a public or synthetic fixture.
2. State the acceptance condition before evaluating the proposed change.
3. Decide whether the behaviour is generic engine method or downstream product
   policy. Product vocabulary, rendering, credentials, and workflow stay with
   the consumer.
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
paths out of commits. The public repository may contain synthetic fixtures,
code, manifests, hashes, and aggregate measurements.

## Pull requests

Use a short-lived branch. Keep each pull request to one coherent capability or
correction, complete the contract and disclosure checklist, and wait for CI.
The compatibility extraction gate, canonical semantic-support gate, and domain
qualification gates are separate; a change to one never silently passes
another.

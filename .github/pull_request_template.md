## What changed

<!-- Describe the smallest coherent change. -->

## Evidence

<!-- Link the issue, frozen fixture, benchmark, or failing test that justified it. -->

## Lane

- [ ] IC product path
- [ ] Canonical core
- [ ] Active experiment
- [ ] Legacy compatibility

## Contract impact

- [ ] No schema, policy, gate, metric, holdout, or public API changed.
- [ ] Any intentional contract change is versioned and documented.
- [ ] No quality claim is borrowed from a different domain or evaluation.
- [ ] No metric or threshold was selected after viewing protected results.
- [ ] Experimental behaviour is not described as a current product stage.

## Determinism and disclosure

- [ ] Deterministic tests do not access the network.
- [ ] New model-backed behaviour is replaceable and benchmark-gated.
- [ ] Outputs retain source, policy, component, and engine identity.
- [ ] The diff contains no credentials, private source text, protected holdout data, or local filesystem paths.

## Validation

```text
python3.12 -m pytest -q
```

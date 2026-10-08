# Inference-cascade experiment

Status: experimental, advisory-only, and outside `groundnut.ic_loop`.

## North star

Let powerful research models make decisions while exposing the few upstream
assumptions and inferences on which those decisions depend.

The experiment asks whether Groundnut can identify a material reasoning error,
show the downstream editorial choices that depend on it, and avoid interrupting
legitimate declared judgment. It does not classify a report as true, replace an
investment decision, or require every analytical statement to be entailed by a
source.

## Current boundary

The prototype consumes a hash-bound
`groundnut-inference-cascade-manifest/v1`. A separate author or reviewer agent
must declare:

- reasoning nodes and report locations;
- the generating reviewer/model protocol identity and hash;
- analytical provenance class;
- dependency edges;
- whether each node is presented as fact, declared judgment, or question;
- its current support assessment, confidence, and materiality.

Groundnut does **not** infer those fields from report prose in this experiment.
That keeps dependency extraction as an explicit unmeasured component rather
than hiding it inside apparently deterministic output.

The resulting `groundnut-inference-cascade-receipt/v1` identifies:

- local integrity, unsupported-fact, and calibration challenges;
- the upstream-most challenge roots;
- downstream nodes and recommendations in each root's blast radius; and
- the distinction between local challenge and downstream impact.

Impact does not relabel a descendant as false. Every receipt declares
`eligible_for_ic_loop: false` and `publication_gate: false`.

## Development objective

Synthetic seeded cases measure:

- root-inference precision and recall;
- downstream impact precision and recall; and
- interruption rate over protected legitimate judgments.

These fixtures test the deterministic challenge-map contract, not automatic
reasoning extraction or semantic-support admission. A representative blinded
report experiment must be preregistered before either capability can approach
the product loop.

## Run the isolated lane

```bash
groundnut-cascade-experiment \
  --report research-report.md \
  --manifest reasoning-manifest.json \
  --out cascade-receipt.json
```

The command has no report-fetching, snapshot-writing, ledger, or publication
authority. The main IC loop neither imports nor invokes it.

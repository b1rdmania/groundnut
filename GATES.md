# Groundnut gate roles

**Decision date: 17 August 2026.** This decision separates two different
quality claims without deleting, weakening, or reinterpreting either metric.

## 1. Compatibility extraction gate

`harness/gate.sh` measures the original compatibility pipeline against the
41-category CUAD taxonomy:

- macro-F1 at least 0.55
- quote grounding at least 0.95
- high-severity precision at least 0.70
- perturbation probe gap not more than +0.05

This gate remains byte-for-byte and threshold-for-threshold the historical
extractor qualification. Its best recorded run still fails macro-F1 and
high-severity precision. It remains public because changing Groundnut's product
scope does not turn that failure into a pass.

The gate now has one explicit role: regression and qualification for the
compatibility extractor and its 41-category playbook. It does not measure
semantic claim support and therefore does not accept or reject the canonical
claim-checking engine.

## 2. Canonical semantic-support gate

Current status: **NOT MEASURED**.

This gate admits an optional support detector, not a whole domain pack. Before
the first learned run, `groundnut-support-probe-plan/v3` freezes:

- exact probe hash and group count
- sampling seed
- safe source-pool and complete exclusion-pool hashes
- context-window size and the hash of the exact per-case context-digest manifest
- baseline and candidate policy keys and exact configuration hashes
- primary metric (`macro_f1` or `accuracy`) and minimum meaningful improvement
- allowed lexical-overlap band for supported paraphrases
- the review-manifest hash and the build attempt number from the probe build
  receipt, so a rebuilt probe cannot be frozen as if it were the first

The present-but-irrelevant candidate batch can be sampled before the plan is
frozen. Only human-adjudicated negatives enter the final probe. The
exact accepted probe hash and N are then frozen before any detector runs.

The same cases and windows run through the exact baseline and each candidate.
A candidate is admissible only if it meets three conditions. It is complete. It
improves the preregistered primary metric by at least the frozen difference. It
does not regress on any material case kind. Cached outputs must reproduce the decision offline.

"Material case kind" is every one of the four kinds, with strict no-regression
on per-kind accuracy, hardcoded in `groundnut/support_admission.py`. It is not a
plan field and cannot be relaxed per plan. Because the exact baseline scores
at or near 1.0 on `verbatim_supported`, a bare learned detector will fail this
rule by construction; only a composed policy that keeps the exact check can
pass. That is the intended boundary.

Accepted review decisions require a recorded reviewer id. Reviewer ids are
attribution, not proof of human review or independence: an author may record
and accept its own decision. Probe builds write a
`groundnut-support-probe-build/v2` receipt recording rows walked, rejected,
ambiguous, the attempt number, and the context-manifest hash later bound into
the frozen plan.

The preregistered plan for the first measurement is
`docs/plans/support-admission-plan-v1.md`. The gate stays NOT MEASURED until
the preregistered review and detector comparison have actually run.

The executable consumer is:

```bash
python3 -m groundnut.support_gate_cli \
  --plan support-plan.json \
  --probe support-pilot-cases.jsonl \
  --baseline exact-run.json \
  --candidate detector-run.json \
  --out admission.json
```

It loads the frozen probe and rejects any run whose gold rows are not exactly
its cases; a run's own `probe_sha256` field is never trusted on its own.
It recomputes scores from the recorded gold and assessment rows instead of
trusting the score field carried by either run.

Until an adjudicated probe exists, this gate cannot report pass or fail. A
missing measurement is not a failure, but it is also not evidence of quality.

## 2a. Canonical artifact-extraction syntax gate

Current status: **ADMITTED** for the frozen supported-syntax pack.

Segmenter version 3 scores `1.000` precision, recall, field accuracy and
location coverage over 20 sanitized claims spanning Markdown, rendered HTML
and structured memo JSON. Fixture and profile bytes are frozen and checked by
the evaluator. The public receipt is
`results/artifact-extraction-admission-v1.json`.

This result admits only the documented syntax contract. It does not establish
representative accuracy on arbitrary reports or malformed markup. Those larger
claims remain unmeasured.

## 2b. Mechanical excerpt-anchoring metrics

Verification metrics v4 keeps the stable anchor outcomes (`found`, `ambiguous`,
`not_found`) while separating the method populations:

- `byte_exact`: the raw excerpt occurs verbatim in the stored evidence window;
- `normalised`: the excerpt occurs only after named case, whitespace, quote,
  dash or punctuation normalisation;
- `fuzzy`: approximate anchoring, still subject to the numeric-token guard.

These metrics measure mechanical presence only. They do not enter or replace
the semantic-support admission gate above, and none is a truth verdict.

## 3. Domain qualification gates

A generic support detector does not prove that Groundnut extracts the right
claims for M&A, procurement, trust obligations, IC research, or another domain.
Each exact domain pack needs its own labelled development set, frozen bar, and
protected holdout before it can move beyond `experimental` evidence maturity.

The compatibility CUAD gate can qualify its legacy 41-category playbook. It
cannot be inherited by the deployed 18-category M&A pack or any other pack.

## Non-swap rule

A change to a gate's role does not permit a change to its history. The compatibility
scores and failure remain published. The support gate starts with a new name,
new task, new schema, and preregistered bar because it measures a genuinely
different claim. Any future change to its metric or threshold must be written
and frozen before affected outputs are scored.

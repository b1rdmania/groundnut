# Groundnut gate roles

**Decision date: 17 August 2026.** This decision separates two different
quality claims without deleting, weakening, or reinterpreting either metric.

## 1. Compatibility extraction gate

`harness/gate.sh` measures the original compatibility pipeline against the
41-category CUAD taxonomy:

- macro-F1 at least 0.55;
- quote grounding at least 0.95;
- high-severity precision at least 0.70;
- perturbation probe gap no greater than +0.05.

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
the first learned run, `groundnut-support-probe-plan/v1` freezes:

- exact probe hash and group count;
- sampling seed;
- safe source-pool and complete exclusion-pool hashes;
- context-window size;
- baseline and candidate policy identities;
- primary metric and minimum meaningful improvement;
- allowed lexical-overlap band for supported paraphrases.

The present-but-irrelevant candidate batch may be sampled before the plan is
frozen, but only human-adjudicated negatives can enter the final probe. The
exact accepted probe hash and N are then frozen before any detector runs.

The same cases and windows run through the exact baseline and each candidate.
A candidate is admissible only if it is complete, improves the preregistered
primary metric by at least the frozen difference, and does not regress on any
material case kind. Cached outputs must reproduce the decision offline.

Until an adjudicated probe exists, this gate cannot report pass or fail. A
missing measurement is not a failure, but it is also not evidence of quality.

## 3. Domain qualification gates

A generic support detector does not prove that Groundnut extracts the right
claims for M&A, procurement, trust obligations, IC research, or another domain.
Each exact domain pack needs its own labelled development set, frozen bar, and
protected holdout before it can move beyond `experimental` evidence maturity.

The compatibility CUAD gate may qualify its legacy 41-category playbook. It
cannot be inherited by the deployed 18-category M&A pack or any other pack.

## Non-swap rule

Changing a gate's role does not permit changing its history. The compatibility
scores and failure remain published. The support gate starts with a new name,
new task, new schema, and preregistered bar because it measures a genuinely
different claim. Any future change to its metric or threshold must be written
and frozen before affected outputs are scored.

# Groundnut documentation

The IC research loop is the product. Documents below are grouped by the role
they play in that loop so experiments and historical compatibility work do not
look like current product stages.

## Product contract

| Document | Status | Purpose |
|---|---|---|
| [Claim ledger](./LEDGER.md) | Current | Phase 4.5 inputs, outputs, buckets and replay contract |
| [Architecture](../ARCHITECTURE.md) | Current | Product boundary, canonical core and authority stop line |
| [Gates](../GATES.md) | Current | Published pass, fail and not-measured states |
| [Analytical provenance](./ANALYTICAL-PROVENANCE.md) | Current | Evidence, assertion, calculation, inference and recommendation classes |
| [Render parity](./PARITY.md) | Optional product check | Evidence survival across authored and rendered artifacts |
| [Artifact extraction](./ARTIFACT-EXTRACTION.md) | Measured syntax contract | Markdown, HTML and memo extraction admission and limits |

## Active experiments

These are candidates for improving the IC loop. They are not canonical product
stages until their frozen admission condition passes.

| Document | Lane |
|---|---|
| [Experiment programme](./EXPERIMENTS.md) | Ordered experiment record and transplant rules |
| [Semantic support](./SUPPORT.md) | Support outcomes, probe construction and admission |
| [Support exploration](./SUPPORT-EXPLORATION.md) | Non-admissible detector exploration results |
| [Structured navigation](./NAVIGATION.md) | Frozen navigation interface and rejected selector results |
| [Annotation](./ANNOTATION.md) | Human review and benchmark interchange |
| [Support admission plan](./plans/support-admission-plan-v1.md) | Draft preregistration; reviewer still TBD |
| [22 August review](./plans/review-2026-08-22.md) | Read-only findings behind the admission guards |
| [Evidence operations plan](./plans/evidence-operations-plan-v1.md) | Execution plan for issues #20–#22 |

## Legacy and history

| Document | Status | Purpose |
|---|---|---|
| [Findings](./FINDINGS.md) | Legacy compatibility evidence | Original CUAD extractor findings and reproduction |
| [Canonicalization map](./MIGRATION.md) | Transition record | What moved from the compatibility extractor into Groundnut |
| [`history/`](./history/) | Superseded | Earlier goals, specifications and logs retained for provenance |

Public `results/` files contain aggregate experiment receipts. Private report
rows, protected corpus text, credentials and holdout contents do not belong in
this repository.

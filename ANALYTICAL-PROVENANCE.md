# Analytical provenance

Groundnut records what kind of statement a claim is without allowing that type
to become a support or truth verdict.

Canonical outputs carry `groundnut-analytical-provenance/v1` beside each claim.

## Canonical classes

| Class | Meaning | Default evidence authority |
|---|---|---|
| `external_evidence` | A factual statement intended to rest on an external source | Unassigned until source authority is declared |
| `company_assertion` | A statement made by the subject or company | `subject_provided` |
| `analyst_calculation` | A result derived from named inputs and a method | `analyst_derived` |
| `analyst_inference` | An interpretation or conclusion drawn by the analyst | `analyst_derived` |
| `recommendation` | A proposed action, condition, or decision | `analyst_derived` |
| `open_question` | A question that remains unresolved | Unassigned |
| `unclassified` | No class was declared | Unassigned |

The seventh value is an honest compatibility state, not a target authoring
class. Groundnut never infers `external_evidence` merely because a citation is
nearby. It never infers independent authority from any provenance class.

`company_assertion` can constrain authority to subject-provided evidence. An
explicit independent authority declaration may still describe the source used
to check it, but the claim remains a company assertion. Provenance, authority,
mechanical anchoring, semantic support, and truth are separate fields.

## Artifact conventions

Structured JSON uses `provenance_class` on each claim. HTML and Markdown may
use these classes inside the claim-bearing block:

- `groundnut-external-evidence`
- `groundnut-company-assertion`
- `groundnut-analyst-calculation`
- `groundnut-analyst-inference`
- `groundnut-recommendation`
- `groundnut-open-question`

The historical `declared_analysis: true` and
`groundnut-declared-analysis` forms map to `analyst_inference`. Conflicting
classes fail closed. A profile may port different host markers, and the full
mapping is included in the artifact-profile hash.

## Denominator-safe metrics

Every report rate emitted by mechanical verification uses
`groundnut-metric-envelope/v1`. The envelope binds:

- metric name and class;
- numerator and denominator;
- the population described by that denominator;
- the derived value.

Verification reports keep exact and fuzzy anchoring separate. A fuzzy-found
excerpt is not collapsed into generic validation work: its count is emitted as
`fuzzy_anchored_excerpts`, its outcome as `fuzzy_found`, and its share of
anchored excerpts as a complete metric envelope.

Citation coverage is also emitted by provenance class. A report with extensive
analyst reasoning can therefore be described without pretending that every
uncited conclusion is a missing external fact.

## Segmentation identity

Claim denominators depend on segmentation. Every artifact extraction therefore
records `groundnut-segmenter-identity/v1`, including its algorithm version,
human-readable strategy per artifact kind, and configuration hash. Canonical
run manifests also bind it as the `claim_segmenter` runtime component.

The engine source revision remains independently hash-bound. A comparison that
changes either the segmenter identity or engine build must disclose that change
before interpreting a metric delta as a report-quality delta.

## Public provenance interface trigger

Do not build or publish a two-text-box provenance tool merely because exact
anchoring works on one report.

The trigger is:

> Analytical-provenance schema v1 and metric-envelope schema v1 are frozen,
> and both reproduce consistently across at least three materially different
> real reports.

The three-report experiment must bind each input, extraction profile,
segmenter, engine build, and output. “Consistent” means the schemas preserve
their intended distinctions and the same input reproduces byte-identical
canonical output; it does not require the reports to have similar rates.

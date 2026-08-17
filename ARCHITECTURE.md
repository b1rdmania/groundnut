# Groundnut canonical engine

Groundnut is the canonical anti-hallucination and checking engine. A host gives
it source documents, a versioned domain pack, and a model backend. Groundnut
returns source-anchored findings, honest coverage, and the evidence disclosure
carried by that pack. It is a standalone engine, not an extraction library
whose roadmap is set by any current deployment.

Canonical responses also acknowledge which categories were evaluated in each
source segment. A missing finding becomes `checked_clear` only when every
segment completed and explicitly acknowledged that category; otherwise the
result is `incomplete`.

## Boundary

### Scope decision — 17 August 2026

Groundnut's remit is deliberately wider than extraction alone. It is the
canonical anti-hallucination system: analysis and verification functions,
versioned domain and policy inputs, deterministic artifacts, source
acquisition, evaluation, annotation and adjudication machinery. This is a
capability boundary, not a size limit.

The current priority is to make those checking guarantees tight and measured.
IC research is a future proving ground and consumer once the engine clears its
own bars. Product ports, deployment rewrites, and public packaging are separate
later decisions; none drives the core roadmap today.

Groundnut owns:

- domain-pack validation and versioned playbook hashes;
- document normalization, segmentation, classification, and extraction;
- backend interfaces and deterministic source anchoring;
- coverage, report, corpus, annotation, and adjudication primitives;
- evaluation and arena interfaces, including frozen policies and provenance.

Groundnut may ship persistence and user interfaces when they directly support
those capabilities—for example a review workbench for benchmark adjudication.
Hosts still own deployment identity, secret custody, and the authority to sign
or publish an output. Source connectors implement Groundnut's acquisition
interface; uploaded files and live web sources enter the same normalized source
record after acquisition.

The stop line is authority, not application shape: Groundnut never infers who
may see data, spend credentials, approve a legal conclusion, or publish an
artifact. Those actions require explicit deployment policy or human authority.
Adapters are opt-in edges: importing or running analysis never performs an
implicit network request.

The built-in adapters cover local text and simple HTTP text/HTML. Paywalls,
unreachable sources, and unsupported PDFs remain explicit failure states.
`SnapshotStore` archives the normalized source with its hash and refuses a
tampered snapshot, allowing IC-style verification against what the writer saw
rather than whatever a live URL serves later.

## Arena

The canonical arena is a deterministic adjudicator, not a model client.
Domain adapters emit review tasks; human or model adapters supply one attack
per frozen policy lens and rulings from distinct families and sessions.
Missing work fails closed, family disagreement is `withheld`, and a report
passes only when every task `stands`. The frozen policy hash travels with the
report so thresholds and lenses cannot be selected after seeing the outcome.

Its concrete consumer is the offline `python -m groundnut.arena_cli` command.
The command consumes frozen JSON/JSONL artifacts, writes a deterministic report,
and exits 0 only when every task stands, 1 for a valid non-passing report, and 2
for invalid input. A host or CI job may act on that status; Groundnut does not
publish, approve, or mutate host workflow state.

## Determinism

The test suite must never touch the network. Network access is blocked by an
autouse test fixture; resolver tests inject a fake opener. Live acquisition is
an explicit runtime operation whose normalized bytes should be snapshotted
before downstream analysis. Model parity tests likewise replay recorded or
synthetic responses rather than calling a live model.

## Artifact ingestion

`groundnut-artifact-profile/v1` maps generic structured fields and rendered
evidence conventions into canonical claims. `extract_artifact` accepts
structured JSON, Markdown citations, and rendered HTML, retaining source
identity, quotes, locators, declared analysis, input hash, profile hash, and
artifact location. The parser does not fetch, anchor, assess support, or assign
a domain outcome; those remain later and independently recorded stages.

Consumer-specific field names and HTML conventions belong in a profile rather
than engine conditionals. Reference apparatus can be excluded explicitly, and
unsupported or malformed artifacts fail rather than silently becoming empty
evidence.

## Run manifest

`groundnut-run-manifest/v2` is the portable receipt for one run. It binds an
immutable engine revision; path-bound shipped-source digest; explicit dirty
state; exact playbook and evidence-manifest hashes; source
and optional snapshot hashes; frozen support/arena policies; runtime component
revisions and configuration hashes; and schema-tagged output artifact hashes.
Collection order is canonicalized, duplicate identities are rejected, and the
manifest carries its own SHA-256.

The manifest contains no credentials and performs no storage or signing. A host
may persist or sign the receipt, but Groundnut only produces deterministic
bytes. Timestamps and host workflow state stay outside its canonical hash.

## Claim verification

Mechanical verification reports citation coverage, source accessibility, and
excerpt anchoring separately. Exact/normalised matching is followed by a fuzzy
bigram window with a numeric guard, so `$14.2M` cannot pass against `$4.2M`
through character similarity alone. An anchored excerpt always carries
`support: not_assessed`; presence is not entailment or truth. Semantic judges
may consume that record through an adapter but cannot rewrite its mechanical
provenance.

Semantic support is a separate, versioned artifact. A support policy pins the
detector adapter, model, revision, package version, confidence threshold, and
policy hash before a run. Its result is one of `supported`, `contradicted`,
`insufficient`, `source_unavailable`, or `not_assessed`. The combined claim
artifact preserves the original mechanical verification beside that semantic
assessment; a detector cannot rewrite an inaccessible source or failed anchor.

The shipped exact-support policy is a deterministic baseline, not a semantic
quality claim. It reports a normalized substring as supported and every absent
claim as insufficient—never contradicted. Optional learned adapters must beat
that baseline on a frozen, domain-relevant development set before adoption.

Detector-transfer cases use the paired contract in `SUPPORT.md`. Each group
crosses support status with substring presence and shares one source origin and
question. Consequently neither substring presence nor class-specific context
selection can produce a valid-looking semantic result.

Optional LettuceDetect and MiniCheck adapters are benchmark surfaces, not
runtime endorsements. They load no dependency at import time, pin immutable
model/package/configuration identity, and map outputs conservatively. Binary or
untyped unsupported output is insufficient evidence, not contradiction.

`run_support_probe` is the deterministic experiment runner. It requires a
`groundnut-support-probe-plan/v2` preregistration, feeds every
detector source-identical windows derived from the paired original offsets and
binds the plan, context, detector, exact policy hash, normalized decisions,
scores, and probe manifest into one self-hashed artifact suitable for the run
manifest.

`check_claims` is the end-to-end engine surface for claim batches. It composes
source resolution, mechanical verification, and one frozen support policy. The
result sorts claim identities, derives completeness and metrics from the rows,
and rejects mixed policies or mismatched mechanical/semantic identities. Its
self-hashed report is a first-class run-manifest artifact.

## Arena task emission

`groundnut-arena-emission-profile/v1` freezes the mechanical rules that turn
inferential, derived, and absence-based conclusions into adversarial-review
tasks. Emission binds the input and profile hashes, gives each task a stable
order-derived identity, and draws context only from the same rendered section.
This prevents evidence from a neighbouring slide or heading from silently
supporting a conclusion.

Emission and adjudication are separate. The emitter proposes what should be
attacked; `groundnut-arena-report/v1` still decides attacks and rulings under a
different frozen policy and retains unattacked, unruled, and withheld states.

## Gate roles

The original four-criterion CUAD gate is the compatibility pipeline's
extraction gate. Its 41-category macro-F1, grounding, high-severity precision,
probe-gap bars, historical results, and protected holdout remain unchanged. It
does not accept or reject the canonical claim checker.

The canonical checker has a separate semantic-support admission gate. That
gate is currently unmeasured and cannot pass until an adjudicated support probe
is frozen. A detector run must match the preregistered plan and beat the exact
baseline by its prespecified difference without regressing on a material case
kind. Finally, each domain pack needs its own labelled quality gate; generic
support competence cannot establish domain extraction coverage. The dated
decision and non-swap rules are in `GATES.md`.

## Evidence maturity

Changing configuration demonstrates portability, not quality. Every domain
pack carries one of four evidence states:

- `experimental` — configuration or demo only;
- `development` — measured on a labelled development set;
- `holdout_qualified` — passed a frozen bar on an unspent holdout;
- `production_approved` — separately approved for a named deployment.

A pack may ship as experimental without a gold set. It must not inherit the
measurements or acceptance bar of another domain.

The shipped registry contains the three checklist configurations already
exercised in the deployment: M&A due diligence, procurement compliance, and
trust obligations. They remain explicitly experimental in Groundnut until
each exact playbook has its own labelled set and frozen bar. Registry lookups
never silently fall back to a different domain.

## Compatibility

`pipeline/` remains the CLI used by the original CUAD evaluation. Its default
prompt and output stay unchanged. Supplying `--domain-pack path.json` activates
the canonical `groundnut-analysis/v1` result with domain identity, playbook
hash, source hash, and exact character anchors.

The playbook hash covers executable job configuration only. The separate
manifest hash also covers evidence status and disclosure, so improving or
withdrawing a quality claim never pretends the extraction job itself changed.

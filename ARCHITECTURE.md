# Groundnut architecture

Groundnut's current product is the evidence-integrity stage in the IC research
loop. The research pipeline gives it a completed Markdown report. Groundnut
acquires and snapshots cited sources, checks the report against those snapshots,
and returns a replayable canonical run plus the three-bucket claim ledger.

The reusable checking contracts exist to make that loop more reliable. New
engine machinery earns priority by closing a measured IC-loop gap; Groundnut is
not being built toward an abstract aspirational engine independently of the
product.

The `groundnut` package still imports the legacy compatibility `pipeline`
package for chunking, extraction, and prompts (`groundnut/engine.py`). Separating
them is open work, not a done fact or a reason for cosmetic relocation.

Compatibility extraction responses (`analyse_text`, the legacy path used by
`pipeline/run.py`) also acknowledge which categories were evaluated in each
source segment. A missing finding becomes `checked_clear` only when every
segment completed and explicitly acknowledged that category. If not, the
result is `incomplete`. The canonical check path does not use coverage
acknowledgements.

## Product boundary

The product path is:

```text
report -> acquire/snapshot -> check citations -> claim ledger
```

Groundnut owns that evidence account. The research pipeline owns thesis
generation, workflow, audience and delivery. Groundnut does not rewrite a
report to improve its ledger distribution, and neither a citation nor a model
score grants publication or investment authority.

Semantic support, question relevance, structured navigation, composition and
arena machinery are active experiments. They remain isolated contracts until a
frozen measurement shows that they improve the product path safely.

## Structured evidence navigation

Navigation sits after deterministic acquisition and before semantic support.
It selects source nodes for later checkers. It does not answer a question or
produce a support verdict. `groundnut-navigation-index/v1` binds a native or
derived tree to exact source offsets and hashes. A navigator returns only node
IDs through `groundnut-navigation-selection/v1`, and exact text is recovered
under `groundnut-navigation-receipt/v1` after every identity is checked.

This boundary permits TreeDex- or PageIndex-style vectorless navigation without
letting a selector's generated prose enter the evidence record. Unknown IDs,
duplicates, oversized selections, selector exceptions, and prompt-budget
breaches fail or abstain explicitly. There is no hidden full-document fallback.
Read `docs/NAVIGATION.md` for the frozen experiment contract and donor lineage.

IC research is the current product loop. Navigation remains an experimental
candidate within it: it is not a stage of the canonical run today.

Groundnut owns:

- domain-pack validation and versioned playbook hashes
- document normalization, segmentation, and (compatibility path) classification
  and extraction
- backend interfaces and deterministic source anchoring
- coverage (compatibility path), corpus, annotation, and adjudication
  primitives; there is no report-producing stage yet
- evaluation and arena interfaces, including frozen policies and provenance

Groundnut can ship persistence and user interfaces when they directly support
those capabilities—for example a review workbench for benchmark adjudication.
Hosts still own deployment identity, secret custody, and the authority to sign
or publish an output. Source connectors implement Groundnut's acquisition
interface. Uploaded files and live web sources enter the same normalized source
record after acquisition.

The stop line is authority, not application shape: Groundnut never infers who
can see data, spend credentials, approve a legal conclusion, or publish an
artifact. Those actions require explicit deployment policy or human authority.
Adapters are opt-in edges: importing or running analysis never performs an
implicit network request.

Structured claim artifacts can carry an optional `verification_question`.
This is the explicit task the cited excerpt is meant to answer. It is retained
as the canonical claim's `question`, bound into support inputs and available to
independent relevance components. Groundnut does not derive it silently from
the claim or report section. Older artifacts without the field remain valid.
Question-dependent components must abstain when it is absent.
Markdown and rendered HTML can carry the same field in an adjacent
`groundnut-verification-question` comment after the citation evidence marker.
Both marker names are profile configuration. A consumer such as an IC writer
can use its own convention. The engine takes no product logic from it.

The built-in adapters cover local text and simple HTTP text/HTML. Paywalls,
unreachable sources, and unsupported PDFs remain explicit failure states.
`SnapshotStore` archives the normalized source with its hash and refuses a
tampered snapshot. A checker therefore works against what the writer saw, not
against what a live URL serves later.

## Arena

The canonical arena is a deterministic adjudicator, not a model client.
Domain adapters emit review tasks. Human or model adapters supply one attack
per frozen policy lens and rulings from distinct families and sessions.
Missing work fails closed, family disagreement is `withheld`, and a report
passes only when every task `stands`. The frozen policy hash travels with the
report so thresholds and lenses cannot be selected after seeing the outcome.

Its concrete consumer is the offline `python -m groundnut.arena_cli` command.
The command consumes frozen JSON/JSONL artifacts and writes a deterministic
report. It exits 0 only when every task stands, 1 for a valid non-passing
report, and 2 for invalid input. A host or CI job can act on that status. Groundnut does not
publish, approve, or mutate host workflow state.

## Determinism

The test suite must never touch the network. Network access is blocked by an
autouse test fixture. Resolver tests inject a fake opener. Live acquisition is
an explicit runtime operation. The engine snapshots its normalized bytes
before downstream analysis. Model parity tests likewise replay recorded or
synthetic responses rather than calling a live model.

## Canonical runner

`run_canonical_check` is the product-facing offline checking surface. One call does five things.
It ingests an artifact and acquires each unique cited source under an explicit
snapshot mode. It performs mechanical and semantic checks. It applies
independently declared evidence authority. It can also emit arena tasks from
the same artifact. `groundnut-canonical-run/v1` binds every nested receipt and carries a
self-hash. It still does not turn support or authority into truth.

`execute_canonical_check` closes the provenance loop. It binds that canonical
run into `groundnut-run-manifest/v2`. The manifest carries the exact engine
build, domain pack, artifact, support, authority and arena policies, detector
configuration, normalized sources, and snapshot bytes. Publication-grade execution rejects a dirty
engine. An all-unsourced or all-unavailable run remains manifestable with an
empty normalized-source list rather than disappearing.

## Snapshot-first acquisition

`SnapshotFirstResolver` makes live-network use a named orchestration choice.
Replay-only runs never call a live resolver. Snapshot-preferred runs fetch only
when no archive exists, then archive a successful response. A present but
invalid snapshot fails closed rather than being hidden by fresh network bytes.
Explicit refresh preserves the previous snapshot when the live attempt fails.

`groundnut-source-acquisition/v2` records whether the result was replayed,
fetched and archived, missing, invalid, or a failed live attempt, together with
the snapshot and normalized source hashes. This receipt is suitable for a run
manifest and separates deterministic replay from marked integration work.

Successful `groundnut-source-snapshot/v2` artifacts bind an explicit evidence
window: original and captured lengths where knowable, truncation state,
extraction method, and the hash of the exact normalized text searched. V1
snapshots remain replayable but their completeness is `unknown`; Groundnut does
not reinterpret a historical missing field as a complete capture.

## Artifact ingestion

`groundnut-artifact-profile/v1` maps generic structured fields and rendered
evidence conventions into canonical claims. `extract_artifact` accepts
structured JSON, Markdown citations, and rendered HTML, retaining source
identity, quotes, locators, verification questions, declared analysis, input
hash, profile hash, and artifact location. The parser does not fetch, anchor,
assess support, or assign
a domain outcome. Those remain later and independently recorded stages.

Consumer-specific field names and HTML conventions belong in a profile rather
than engine conditionals. Reference apparatus can be excluded explicitly, and
unsupported or malformed artifacts fail rather than silently becoming empty
evidence.

Artifact ingestion also preserves an explicit analytical-provenance class.
External evidence, company assertions, analyst calculations, analyst
inferences, recommendations, and open questions remain distinct. The class can
constrain evidence authority but cannot upgrade mechanical anchoring or
semantic support. Legacy declared-analysis markers map to analyst inference.
Untyped material remains `unclassified`. The engine does not guess it from
nearby citations.

Every extraction records a separately versioned and hashed segmenter identity,
its claim count, and the artifact-profile hash. The canonical manifest binds the
segmenter as a runtime component in addition to the complete engine-source
hash. Claim-denominated comparisons must disclose a changed segmenter or engine
build.

## Render-bound evidence parity

`groundnut-render-receipt/v1` proves that the ordered sequence of source URI,
exact excerpt, and locator survived from an authored artifact into a rendered
artifact. It binds both artifact hashes and extraction profiles, both segmenter
identities, the renderer name/version/configuration hash, claim counts, and the
complete evidence-sequence hash. Any loss, reorder, or quote/locator drift fails
before a receipt is produced.

Renderer chrome can be excluded only through attributes or classes named in the
hashed artifact profile. The default explicit attribute is
`data-groundnut-evidence-exclude`. Report prose is never implicitly excluded.
The receipt computes no evidence state, semantic verdict, publication gate, or
recommendation. Groundnut owns the generic comparison. Host projects continue
to own rendering, presentation, audience, and publication authority.

## Run manifest

`groundnut-run-manifest/v2` is the portable receipt for one run. It binds:

- an immutable engine revision
- a path-bound shipped-source digest and explicit dirty state
- exact playbook and evidence-manifest hashes
- source and optional snapshot hashes
- frozen support and arena policies
- runtime component revisions and configuration hashes
- schema-tagged output artifact hashes
Collection order is canonicalized, duplicate identities are rejected, and the
manifest carries its own SHA-256.

The manifest contains no credentials and performs no storage or signing. A host
can persist or sign the receipt, but Groundnut only produces deterministic
bytes. Timestamps and host workflow state stay outside its canonical hash.

## Claim verification

Mechanical verification reports citation coverage, source accessibility, and
excerpt anchoring separately. Exact/normalised matching is followed by a fuzzy
bigram window with a numeric guard, so `$14.2M` cannot pass against `$4.2M`
through character similarity alone. An anchored excerpt always carries
`support: not_assessed`. Presence is not entailment or truth. Semantic judges
can consume that record through an adapter but cannot rewrite its mechanical
provenance.

Every mechanical verification rate is a metric envelope carrying its
numerator, denominator, population, and metric class. Fuzzy-found excerpts are
reported separately from exact anchors and from absent sources. Coverage is
also grouped by analytical-provenance class, preventing an uncited analyst
inference from being silently counted as the same failure as an uncited
external fact.

An `analyst_calculation` can also carry
`groundnut-calculation-lineage/v1`: an exact formula hash, unique named input
values, and optional references to other claims in the same artifact. Missing
lineage is an explicit state. Formula declaration never upgrades support.

Semantic support is a separate, versioned artifact. A support policy pins the
detector adapter, model, revision, package version, confidence threshold, and
policy hash before a run. Its result is one of `supported`, `contradicted`,
`insufficient`, `source_unavailable`, or `not_assessed`. The combined claim
artifact preserves the original mechanical verification beside that semantic
assessment. A detector cannot rewrite an inaccessible source or failed anchor.

The shipped exact-support policy is a deterministic baseline, not a semantic
quality claim. It reports a normalized substring as supported and every absent
claim as insufficient—never contradicted. Optional learned adapters must beat
that baseline on a frozen, domain-relevant development set before adoption.

Detector-transfer cases use the paired contract in `docs/SUPPORT.md`. Each group
crosses support status with substring presence and shares one source origin and
question. Consequently neither substring presence nor class-specific context
selection can produce a valid-looking semantic result.

Optional LettuceDetect and MiniCheck adapters are benchmark surfaces, not
runtime endorsements. They load no dependency at import time, pin immutable
model/package/configuration identity, and map outputs conservatively. Binary or
untyped unsupported output is insufficient evidence, not contradiction.

`run_support_probe` is the deterministic experiment runner. It requires a `groundnut-support-probe-plan/v3` preregistration. It feeds every
detector source-identical windows derived from the paired original offsets. It
binds the plan, context, detector, exact policy hash, normalized decisions,
scores, and probe manifest into one self-hashed artifact. That artifact suits
the run manifest.

`check_claims` is the end-to-end engine surface for claim batches. It composes
source resolution, mechanical verification, and one frozen support policy. The
result sorts claim identities, derives completeness and metrics from the rows,
and rejects mixed policies or mismatched mechanical/semantic identities. Its
self-hashed report is a first-class run-manifest artifact.

## Evidence authority

`groundnut-evidence-authority/v1` records whether evidence is independent
primary, independent secondary, subject-provided, analyst-derived, or of
unknown authority. The assignment and its policy/declaration hashes sit beside
mechanical verification and semantic support. They never overwrite either.

An exact or learned detector can therefore return `supported` for identical
text under two different authority assessments. A downstream domain can treat
those cases differently, but Groundnut does not convert authority plus support
into truth or a product verdict. Missing authority remains
`unknown_authority`, and explicit analyst derivation remains unassessed for
semantic support unless separately checked.

## Arena task emission

`groundnut-arena-emission-profile/v1` freezes the mechanical rules that turn
inferential, derived, and absence-based conclusions into adversarial-review
tasks. Emission binds the input and profile hashes, gives each task a stable
order-derived identity, and draws context only from the same rendered section.
This prevents evidence from a neighbouring slide or heading from silently
supporting a conclusion.

Emission and adjudication are separate. The emitter proposes what must be
attacked. `groundnut-arena-report/v2` still decides attacks and rulings under a
different frozen policy. It retains unattacked, unruled, and withheld states.

## Gate roles

The original four-criterion CUAD gate is the compatibility pipeline's
extraction gate. Its 41-category macro-F1, grounding, high-severity precision,
probe-gap bars, historical results, and protected holdout remain unchanged. It
does not accept or reject the canonical claim checker.

The canonical checker has a separate semantic-support admission gate. That
gate is currently unmeasured and cannot pass until an adjudicated support probe
is frozen. A detector run must match the preregistered plan and beat the exact
baseline by its prespecified difference without regressing on a material case
kind. Finally, each domain pack needs its own labelled quality gate. Generic
support competence cannot establish domain extraction coverage. The dated
decision and non-swap rules are in `GATES.md`.

## Evidence maturity

Changing configuration demonstrates portability, not quality. Every domain
pack carries one of four evidence states:

- `experimental` — configuration or demo only
- `development` — measured on a labelled development set
- `holdout_qualified` — passed a frozen bar on an unspent holdout
- `production_approved` — separately approved for a named deployment.

A pack can ship as experimental without a gold set. It must not inherit the
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

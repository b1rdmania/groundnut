# Groundnut canonical engine

Groundnut is the reusable, checklist-driven document-intelligence method. A
host gives it source documents, a versioned domain pack, and a model backend.
Groundnut returns source-anchored findings plus the evidence disclosure carried
by that pack.

Canonical responses also acknowledge which categories were evaluated in each
source segment. A missing finding becomes `checked_clear` only when every
segment completed and explicitly acknowledged that category; otherwise the
result is `incomplete`.

## Boundary

Groundnut owns:

- domain-pack validation and versioned playbook hashes;
- document normalization, segmentation, classification, and extraction;
- backend interfaces and deterministic source anchoring;
- coverage and report primitives that do not depend on an application database;
- evaluation and arena interfaces, including frozen policies and provenance.

Hosts own authentication, persistence, credentials, user interfaces, and the
decision to sign or publish an output. Source connectors implement Groundnut's
acquisition interface; uploaded files and live web sources enter the same
normalized source record after acquisition.

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

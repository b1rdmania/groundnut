# Groundnut

**Groundnut is the evidence-integrity stage in the investment-committee research loop.**

> **Security status: work in progress.** Groundnut has not completed a
> comprehensive security review. Live acquisition now has scheme, destination,
> redirect, connection-pinning and resource-limit controls, and PDF parsing runs
> in a separately bounded worker. These controls are awaiting independent
> security review and must not be presented as a completed security posture.
> See the [security hardening plan](./docs/plans/security-hardening-plan-v1.md).

A pitch deck enters the research pipeline. The pipeline produces a research
report, then calls Groundnut before delivery. Groundnut snapshots the cited
sources, checks every citation against what was fetched, and produces a claim
ledger that makes unsupported extrapolation visible.

```text
pitch deck
    |
    v
research pipeline -> report draft
                         |
                         v
               Groundnut (Phase 4.5)
               - snapshot sources
               - verify quoted evidence
               - classify report units
               - bind the run for replay
                         |
                         v
              final report + claim ledger
```

The claim ledger puts each report unit in one of three buckets:

| Bucket | Meaning |
|---|---|
| `excerpt_found` | The quoted words were found in the source snapshot. |
| `citation_unconfirmed` | A citation exists, but its quotation could not be confirmed. |
| `own_reasoning` | The report makes an uncited statement or declared inference. |

“Verified” means quotation presence, not truth. Groundnut keeps source access,
quotation presence, semantic support, evidence authority, and truth separate.

## What works today

- Markdown research reports are checked against their cited web and PDF sources.
- Successful live fetches are normalized and snapshotted for offline replay.
- Shared HTTP acquisition permits only public HTTP(S) destinations, rechecks
  redirects, pins each connection to a validated address while preserving TLS
  hostname verification, bounds encoded and decoded response bytes, and
  restricts admitted media. PDF parsing runs in a worker with wall-clock, CPU,
  resident-memory and output ceilings. These controls reduce known SSRF and
  denial-of-service exposure; they are not a completed security review.
- Declared read-time producers bind connector intent and allowed media classes
  into a capture receipt, preserve the first read, and omit connector secrets.
- Snapshots disclose the exact searched evidence window, its extraction method,
  and whether capture was complete, truncated, empty, sparse, hollow, or
  historically unknown.
- Byte-exact and named-normalisation quotation anchoring are the only methods
  that establish mechanical presence. Fuzzy similarity is diagnostic-only and
  preserves ambiguity; none is a semantic-support or truth judgment.
- Bare locators for confidential or physical sources remain in the claim
  population as explicitly unresolvable evidence instead of becoming uncited
  own reasoning.
- A missing excerpt is reported as `evidence_window_incomplete` instead of
  `excerpt_not_found` when the stored window could have hidden it.
- `groundnut-equivalence` compares the evidence content of a live run with its
  replay and requires a second replay to be byte-identical, while naming every
  deliberately excluded acquisition field.
- The report, source snapshots, policies, engine revision, run and ledger are
  hash-bound.
- Numeric own-reasoning units are separated as a reading aid for likely
  extrapolation.
- Empty or malformed claim populations cannot pass the numeric gate as clear.
- Table cells enter the claim population; excluded Markdown regions and parser
  anomalies are counted in the ledger.
- Annotation conflicts are exposed without hard-coding a consuming product's
  writing policy into the engine.
- Segmenter v5 Markdown, nesting-aware rendered HTML and structured memo extraction pass the frozen
  20-claim supported-syntax admission pack with `1.000` precision, recall,
  field accuracy and location coverage. This is conformance evidence, not a
  representative arbitrary-document accuracy claim. Expected structured-row,
  Markdown-line and normalized-HTML locations are part of the frozen gold.
- The last preserved RxClarity population measurement was produced on `a3`:
  567 units, 105 citation-bearing (18.5%), 462 own reasoning, and 125 undeclared
  numerics. It is historical context, not an `a4` or later measurement.

Groundnut does not currently decide that a paraphrase is semantically supported
or contradicted. The learned semantic-support gate is **NOT MEASURED** and only
the mechanical byte-exact/normalised anchoring baseline is admitted. Approximate
similarity remains an ambiguity diagnostic. A
high own-reasoning share is a finding about a report, not a pipeline failure,
and the pipeline must not edit the report merely to improve that number.

The operational contract and output files are documented in
[Claim ledger](./docs/LEDGER.md). The cross-format measurement and its limits
are documented in [Artifact extraction](./docs/ARTIFACT-EXTRACTION.md), and the
producer boundary in [Declared read-time capture](./docs/READ-TIME-CAPTURE.md).

## Install for an integration

Groundnut is currently an alpha package. Pin the exact revision used by a host:

```bash
python3.12 -m pip install "groundnut-evidence @ git+https://github.com/b1rdmania/groundnut.git@<commit>"
groundnut-ic --help
```

The installed commands use bundled, versioned IC defaults and do not depend on
a developer checkout path. A release tag is created only from a clean, tested
revision.

## Product path

The current canonical product path is deliberately small:

```text
report -> acquire/snapshot -> check citations -> claim ledger
```

`groundnut.ic_loop` is the Phase 4.5 orchestration surface. Underneath it,
`groundnut.canonical_cli` produces the replayable canonical run and
`groundnut.ledger_cli` produces the reader-facing ledger.

The stable integration boundary is the versioned JSON carried by those CLIs.
Python package-root exports are implementation conveniences, not a promise that
every experimental class is a stable public API.

Groundnut owns evidence acquisition, normalized snapshots, claim extraction,
quotation anchoring, analytical provenance, support-policy execution and the
ledger. The research pipeline owns thesis generation, audience, workflow and
delivery. Humans retain publication and investment authority.

## Experimental lanes

Groundnut also contains active experimental machinery. It is here to earn its
way into the product path, not to define an aspirational architecture:

- **Semantic support:** paraphrase, contradiction and insufficiency detectors,
  with a preregistered human-reviewed admission gate.
- **Question relevance:** whether cited evidence answers an explicit verification
  question. It cannot fire usefully until the research artifact supplies real
  questions rather than boilerplate.
- **Structured navigation:** selection over frozen source structure. The current
  small-model selector is rejected; the interface remains available for a
  stronger measured candidate.
- **Decision and adversarial review:** shadow composition and arena contracts.
  These are not stages of the current IC loop.

No experimental result changes the canonical product path until its frozen gate
passes. See [Experiments](./docs/EXPERIMENTS.md),
[Semantic support](./docs/SUPPORT.md), and
[Navigation](./docs/NAVIGATION.md).

## Legacy compatibility

`pipeline/` and `harness/` preserve the original CUAD contract-extraction path
and its historical four-bar gate. That gate still fails its published macro-F1
and high-severity precision bars. It is retained for provenance and regression
coverage; it is not Groundnut’s product acceptance test.

The compatibility code remains imported by `groundnut.engine`. Removing that
dependency is open work and will be done only when the IC path no longer relies
on it—not as a cosmetic directory shuffle.

## Rules that do not move

- **Evidence before confidence.** A score cannot repair missing evidence.
- **Fail closed.** Missing sources, invalid outputs and disagreement remain visible.
- **Replay everything.** Material inputs, policies, components and outputs have
  stable identities and hashes.
- **Earn every quality claim.** A configuration does not inherit another
  domain’s result.
- **Freeze before scoring.** Cases, metrics, thresholds and stopping rules are
  fixed before an admission run.
- **No network in deterministic tests.** Live acquisition is explicit and
  successful results are snapshotted.
- **Publish aggregates, not protected data.** Private reports and protected
  corpus rows stay outside this repository.

## Repository map

| Area | Status | Purpose |
|---|---|---|
| `groundnut/ic_loop.py`, `ledger.py`, `canonical_cli.py`, `runner.py` | Product | Current IC evidence-integrity path |
| `groundnut/equivalence.py` | Product conformance | Live/replay evidence comparison and deterministic replay receipt |
| `groundnut/capture.py` | Product integration | Declared first-read source capture and secret-safe receipt |
| `groundnut/artifacts.py`, `sources.py`, `verification.py`, `authority.py` | Canonical core | Shared contracts used by the product path |
| `groundnut/support_*`, navigation, relevance, signals and arena modules | Experimental | Measured candidates and admission machinery |
| `scripts/` | Experimental operations | Reproducible preparation, evaluation and review commands |
| `pipeline/`, `harness/` | Legacy compatibility | Original CUAD extractor and historical gate |
| `domains/`, `profiles/`, `policies/` | Configuration | Versioned product and experiment inputs |
| `results/` | Public evidence | Aggregate experiment receipts, never private rows |
| `tests/` | Conformance | Offline deterministic suite |
| `docs/` | Documentation | Product contracts, gates, experiments, plans and history |

The documentation index is [docs/README.md](./docs/README.md).
[ARCHITECTURE.md](./ARCHITECTURE.md) describes ownership and invariants;
[GATES.md](./GATES.md) records exactly what is measured, failed or still open.

## Repository status

Groundnut is an internal working repository published for transparency. It is
not packaged or supported as a general-purpose end-user installation. The
development contract is Python 3.12 with an offline deterministic test suite;
contribution rules are in [CONTRIBUTING.md](./CONTRIBUTING.md).

The CUAD corpus, protected holdouts, private pitch decks, research reports and
claim-ledger rows are not redistributed. Public receipts contain hashes and
aggregate measurements only.

## Licence and attribution

Groundnut code is Apache 2.0. See [LICENSE](./LICENSE).

Explored third-party components retain their own licences and are not admitted
merely because an adapter exists. The compatibility corpus is CUAD v1,
copyright The Atticus Project, licensed under CC BY 4.0; its contract text is
not redistributed.

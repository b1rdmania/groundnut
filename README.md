# Groundnut

**Groundnut is the canonical evidence and claim-checking engine for AI systems
that must show their work.**

It takes claims, questions, sources, and a frozen checking policy. It returns a
replayable account of what the evidence supports, contradicts, leaves
incomplete, or cannot assess.

Groundnut does not decide that a claim is true because a quotation exists.
Presence, relevance, support, authority, completeness, and truth are different
questions. The engine keeps them separate.

## North star

Groundnut is the reusable control plane between model-generated work and
consequential use.

```text
claims + evidence universe + frozen policy
                    |
                    v
       canonical, source-bound decisions
                    |
                    v
 support | contradiction | insufficiency | access failure | unassessed
                    |
                    v
       hashes | offsets | provenance | replay | explicit uncertainty
```

The goal is not one perfect model. Groundnut can combine deterministic checks,
navigation, relevance, entailment, contradiction, and adversarial review. Each
part must remain labelled, pinned, measured, replayable, and removable.

Products supply domain policy, credentials, audience, and presentation. They
should not rebuild the checking engine.

## Where it stands, in plain English

Groundnut has a strong control system and an unfinished semantic judge.

- The engine can ingest reports, preserve citations, snapshot sources, anchor
  excerpts, record provenance, run component signals, abstain safely, and
  reproduce its decisions.
- The original contract extractor remains as a compatibility pipeline. Its
  published gate still fails. Groundnut does not hide or reinterpret that
  result.
- The canonical semantic-support gate is **NOT MEASURED**. The required
  human-adjudicated benchmark is not complete, so Groundnut makes no production
  quality claim for semantic support.
- Seven learned approaches have been explored. None is admitted as the final
  judge. AlignScore is the strongest complete-label candidate. Extractive QA is
  the strongest independent relevance candidate.
- Structured navigation now has a strict, hash-bound interface. Short handles
  increased exact evidence coverage from 3/100 to 13/100 with Qwen3 0.6B. That
  model is still rejected because 13% recall is unsafe.
- The first private IC report proved that the controls can catch quote drift
  and prevent evidence loss during rendering. It did not prove semantic
  accuracy.

The immediate job is to measure the semantic-support layer properly. The next
navigation job is to test a stronger selector against the same frozen 100-case
pack without changing the interface.

## Engine shape

```mermaid
flowchart LR
    A["Source reference or file"] --> B["Resolve and snapshot"]
    B --> C["Navigate frozen source structure"]
    C --> D["Segment and extract claims"]
    D --> E["Exact, numeric and attribution checks"]
    E --> F["Relevance, support and contradiction signals"]
    F --> G["Groundnut decision and abstention policy"]
    G --> H["Frozen-policy arena"]
    H --> I["Source-bound report, manifest and gate"]
```

Groundnut owns:

- acquisition, snapshots, navigation, segmentation, and exact source anchors;
- mechanical checks and separate relevance, support, contradiction, and
  authority signals;
- versioned domain packs, analytical provenance, and calculation lineage;
- frozen decision, abstention, and adversarial-review policies;
- render-parity checks that stop evidence disappearing from delivered reports;
- one replayable manifest for sources, policies, components, and outputs.

Groundnut does not own deployment identity, credentials, publication
authority, or final human sign-off. It may grow a review interface or storage
layer when that directly improves checking quality. The boundary is authority,
not code size. See [ARCHITECTURE.md](./ARCHITECTURE.md).

## Rules that do not move

- **Evidence before confidence.** A high score cannot repair missing evidence.
- **Fail closed.** Missing sources, missing checks, invalid model output, and
  judge disagreement remain visible.
- **Replay everything.** Every material input, policy, component, decision, and
  output has an identity and hash.
- **Earn every quality claim.** A portable configuration does not inherit
  another domain's score.
- **Freeze before scoring.** Cases, policies, thresholds, metrics, and stopping
  rules are fixed before an admission run.
- **No network in deterministic tests.** Live acquisition is explicit and its
  successful output is snapshotted.
- **Publish numbers, not protected data.** Corpora and private report rows stay
  outside this repository.

## Measured, replaceable components

Groundnut adopts useful mechanisms, not donor product claims. External
components produce typed signals. Groundnut preserves their raw outputs and
owns the final decision.

Groundnut has explored TreeDex, PageIndex, AlignScore, MiniCheck,
LettuceDetect, SummaC, BGE rerankers, extractive QA, semchunk, OpenContracts,
and Inspect AI. No learned component is admitted as the semantic judge.
Selectable-only navigation handles are retained as infrastructure, but the
tested Qwen3 0.6B selector is rejected.

The measurements and donor decisions live in
[EXPERIMENTS.md](./EXPERIMENTS.md),
[SUPPORT-EXPLORATION.md](./SUPPORT-EXPLORATION.md), and
[NAVIGATION.md](./NAVIGATION.md). Public aggregate receipts live in `results/`.

## Three separate gates

Groundnut does not swap a metric after seeing a result:

1. **Compatibility extraction gate.** This is the original 41-category CUAD
   extractor gate. Its best recorded run still fails macro-F1 and
   high-severity precision.
2. **Canonical semantic-support gate.** Current state: **NOT MEASURED**. It can
   change only after a preregistered run on accepted, human-reviewed cases.
3. **Domain qualification gates.** Each exact domain pack needs its own labelled
   development set and protected holdout. Configuration portability is not
   evidence of quality.

The exact bars, results, and grounding caveats remain public in
[GATES.md](./GATES.md) and [FINDINGS.md](./FINDINGS.md).

## Run it

```bash
python3.12 -m pytest -q

# canonical claim-checking process boundary
python3 -m groundnut.canonical_cli \
  < canonical-request.json > canonical-response.json
```

`groundnut.canonical_cli` is the stable JSON boundary for Python, TypeScript,
and other hosts. Replay-only acquisition is the default. Live acquisition must
be enabled explicitly, and successful live results are archived before replay.
Only the frozen exact-support baseline is admitted while the support gate is
unmeasured.

The CUAD corpus and gold answers are not in this repository. Rebuild the corpus
from its manifest with `scripts/fetch_corpus.py`. Do not spend the protected
holdout until a preregistered development gate passes.

Specialist CLIs for compatibility extraction, support evaluation, arena
adjudication, annotation, navigation, and render parity are documented beside
their contracts.

## Repository guide

| Path | Purpose |
|---|---|
| `groundnut/` | Canonical engine, contracts, policies, provenance, and CLIs |
| `domains/` | Versioned domain packs and evidence-maturity disclosures |
| `policies/` | Frozen support and arena policies |
| `pipeline/`, `harness/` | Compatibility extractor and historical gate |
| `tests/` | Offline deterministic conformance suite |
| `results/` | Public aggregate experiment results; never private source rows |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Scope, authority boundary, and invariants |
| [EXPERIMENTS.md](./EXPERIMENTS.md) | Experiment order, transplant rules, and decisions |
| [SUPPORT.md](./SUPPORT.md) | Semantic-support contracts and admission protocol |
| [NAVIGATION.md](./NAVIGATION.md) | Structured-navigation contracts and N1-N3 results |
| [GATES.md](./GATES.md) | Compatibility, semantic-support, and domain gate roles |
| [ANNOTATION.md](./ANNOTATION.md) | LegalBench-RAG and OpenContracts review workflow |
| [ANALYTICAL-PROVENANCE.md](./ANALYTICAL-PROVENANCE.md) | Evidence, assertion, calculation, inference, and recommendation types |

## Downstream use

IC research is the first private proving ground. It does not set Groundnut's
architecture and it is not a production cutover. Atlas, other product v2s, and
operating-system ports are possible later consumers.

Hosts can integrate through the canonical JSON boundary and domain profiles.
They should keep private company data, credentials, audience rules, and
publication decisions outside this public repository.

## Licence and attribution

Groundnut code is Apache 2.0. See [LICENSE](./LICENSE).

The compatibility corpus is CUAD v1, copyright The Atticus Project, licensed
under CC BY 4.0. Groundnut does not redistribute the contract text.

> Hendrycks, Burns, Chen and Ball. *CUAD: An Expert-Annotated NLP Dataset for
> Legal Contract Review.* NeurIPS 2021.

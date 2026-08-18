# Composable-engine experiment programme

**Decision date: 18 August 2026.**

Groundnut may combine many external components. It does not inherit their
claims. Groundnut owns the shared contracts, evidence record, final decision,
abstention, evaluation, and replay.

The aim is a well-governed composed engine:

- take useful mechanisms, not product claims;
- preserve each component's normalised raw output;
- pin code, model, licence, configuration, and input identity;
- compare every component on identical cases;
- keep signals separate until a frozen Groundnut policy combines them;
- retain a weak component when it adds a distinct useful signal;
- remove any component without changing the evidence contract.

## The target path

```text
source acquisition
    -> deterministic snapshot
    -> structured evidence navigation
    -> evidence windows
    -> exact, numeric and attribution checks
    -> question relevance
    -> support and contradiction signals
    -> Groundnut decision and abstention policy
    -> arena attacks
    -> source-bound report and replay receipt
```

This is a build order, not a claim that every stage is already accurate.

## Experiment lanes

Groundnut keeps three lanes separate.

| Lane | Purpose | May change the canonical gate? |
|---|---|---|
| Component exploration | Learn what one mechanism contributes | No |
| Policy development | Combine frozen component outputs on development cases | No |
| Admission | One preregistered run on human-reviewed cases | Yes |

Agent-screened cases remain in component exploration. Looking at their results
does not turn them into gold labels. The protected admission set is not used to
select components, thresholds, rules, or stopping points.

## Common transplant contract

Before a component can join an experiment, its adapter must emit a
`groundnut-component-signal/v1` artifact with:

- one explicit role, such as relevance, entailment, contradiction, unsupported
  detection, span localisation, segmentation, or arena attack;
- the existing immutable detector identity;
- code and model licence records;
- a hash of the exact source, claim, and question input;
- named scores with stable meanings;
- the normalised raw output and its hash;
- a plain statement of what the signal does and does not decide.

A component signal is not a support verdict. A `groundnut-signal-bundle/v1`
may carry several signals for the same input without collapsing disagreement.

## Ordered experiments

### N1 — structured evidence navigation

Before support judging, compare full injection, a transparent lexical floor,
and a TreeDex-style one-shot node selector on the same 100 LegalBench-RAG cases.
Expert answer offsets define the required nodes; all sources are unique and
excluded from the protected holdout. Freeze seed 991, paragraph indexer v1,
3,000-character nodes, at most five model-selected nodes, and fail-closed output
validation before the model run.

Primary safety metric: exact coverage of every required node. Efficiency
metrics: selected and irrelevant nodes, fetched context characters, and context
ratio. Abstention, invalid output, prompt-budget overflow, and missing evidence
remain separate. This is a development selection experiment, not a support or
answer-quality gate.

The deterministic controls show that full injection covers 100/100 cases at a
mean 98.90% context ratio, while the max-three lexical selector covers only
8/100 at 6.06%. The lexical method is therefore rejected despite its token
saving.

The strict Qwen3 0.6B TreeDex-style arm covered 3/100 cases. It returned 24
valid bounded selections, abstained 23 times, and failed 53 times; 51 failures
were unknown or non-selectable IDs. When it selected, it used a mean 8.30% of
source context, but context reduction cannot compensate for missed evidence.
Reject this arm. Next compare short selector handles and native hierarchy with
the flat index, then test a stronger selector on the identical development
pack. The aggregate is `results/navigation-n1-v1-summary.json`; see
`NAVIGATION.md` for contracts and reproduction.

### E0 — common signal receipts

Implement the component signal and bundle schemas. Migrate benchmark adapters
to them without changing their published exploratory decisions.

Exit condition: the same input and component output reproduce byte-identical
signal and bundle hashes offline.

Current state: complete. The signal and bundle schemas have landed. AlignScore,
MiniCheck, LettuceDetect, and SummaC emit the same complete receipt without
changing their detector labels or normalised raw-output hashes.

### E1 — SummaC sentence-pair aggregation

Add a benchmark-only SummaC adapter. Record its published aggregate consistency
score as a support signal. Do not let its binary score type a contradiction or
answer question relevance.

Compare it on the existing 184 exploratory cases. Report all four case kinds,
not only aggregate accuracy.

Stop if it duplicates AlignScore and MiniCheck without improving any material
case kind or useful disagreement pattern.

Result: keep only as an offline challenger signal. SummaC-ZS reached 43.5%
three-way accuracy, 0.240 macro-F1, 66.3% binary accuracy, and 45.7%
unsupported recall on the same 184 exploratory cases. It marked 42/46
contradictions as unsupported, including seven that MiniCheck missed, but typed
no contradictions and found 0/46 present-but-irrelevant cases. The local CPU
run took about 24 minutes and used about 2 GB resident memory. This is useful
development evidence and not an admission result.

### E2 — controlled evidence-window comparison

Compare the current segmenter with semchunk on the same documents, claims,
model backend, context budget, and merge policy. Include the largest contracts
and record offset preservation, claim coverage, runtime, and merge failures.

Do not replace the current segmenter from an uncontrolled cross-run score.

E2A structural result: do not adopt semchunk 4.1.1 with the tested
20,000-character limit and 500-character overlap. The hash-bound run used all
306 safe development contracts, including the ten largest, and 2,062 frozen
grounded quotes from the 80-document working set. Both methods preserved all
non-whitespace source text. The current splitter produced 978 windows, kept all
2,062 quotes inside at least one window, and created 243 duplicate quote
exposures. semchunk produced 1,494 windows, kept 2,060 quotes inside a window,
cut two long quotes at boundaries, and created 285 duplicate exposures. Its
measured segmentation time was 1.21 seconds instead of 0.005 seconds.

This is a structural result, not an extraction-quality result. It does not
authorise a segmenter change. The committed summary is
`results/segmentation-e2-v1-summary.json`; the full row-level receipt is bound
by SHA-256 in that summary. A same-backend extraction comparison is E2B and
should run only for a candidate configuration that first clears the structural
regressions.

### E3 — independent question relevance

Build relevance as its own signal. Its question is: “Does this evidence answer
the stated question?” It must not infer that a relevant answer supports the
claim.

The primary development target is present-but-irrelevant evidence. The current
best exploratory result is 8 of 46. Supported-claim recall is a material guard,
not an optional trade.

E3A corrects the measurement contract. Contradictory evidence is still
relevant when it answers the question, so verbatim support, paraphrased support,
and contradiction are the three relevant cases. Present-but-irrelevant is the
negative case. The scorer sees only the question and the candidate evidence;
it cannot use a different answer elsewhere in the context window. Results are
threshold-free because no operating point was preregistered.

The transparent lexical floor reached ROC-AUC 0.602 and ranked all three
relevant cases above the irrelevant case in 17 of 46 paired groups. The pinned
MIT `BAAI/bge-reranker-base` model reached ROC-AUC 0.613 and separated all four
cases in 23 groups. The stronger Apache-2.0 `BAAI/bge-reranker-v2-m3` reached
ROC-AUC 0.676 and separated 27 groups. Its pairwise win rates were 32/46 for
verbatim support, 34/46 for paraphrase, and 29/46 for contradiction. This is
material movement and still not an adoption result. Keep v2-m3 as an offline
challenger and keep searching. The committed summary is
`results/relevance-e3-v1-summary.json`.

E3B tested extractive answerability. Pinned
`deepset/roberta-base-squad2` reached ROC-AUC 0.750 and separated 31 of 46
complete groups. Its pairwise win rates were 39/46 for verbatim support, 40/46
for paraphrase, and 35/46 for contradiction. This is the leading
question-relevance challenger and remains exploratory rather than admitted.

E3C applied BGE v2-m3 to 96 claim/excerpt pairs from one private IC report. It
was an unlabelled envelope, not a benchmark. Exact, ambiguous and failed fuzzy
anchor strata all had high median semantic-relatedness scores. Semantic
relevance therefore cannot repair or replace mechanical anchoring. The public
aggregate receipt is `results/ic-relevance-envelope-v1-summary.json`; the
row-level receipt remains private. Current IC claim records have no verification
question, so future profiles need that field before applying extractive QA.

E3D composed the existing mechanical run, exact support baseline, and all 96
unlabelled component observations over the same private report. The report had
105 claims and no explicit verification questions. The fail-closed shadow
policy retained 10 source-unavailable results, 32 inconclusive anchors as
`needs_validation`, and withheld a semantic outcome for the other 63 claims.
It did not reinterpret the older report's prose as a question and did not let
high learned scores repair anchoring. The aggregate is
`results/ic-composed-shadow-v1-summary.json`; the self-hashed row receipt stays
private.

### E4 — frozen multi-signal policy

The pre-admission shadow composer now preserves mechanical anchoring, the exact
baseline, and arbitrary experimental signals under explicit fail-closed rules.
It emits `source_unavailable`, `needs_validation`, `not_assessed`, or
`withheld`; it does not average uncertainty away. The first private replay is
E3D.

Next, compose exact, numeric, attribution, relevance, AlignScore, SummaC,
MiniCheck, and LettuceDetect signals behind a frozen admission policy. A
component may influence an outcome only after its own gate passes.

Freeze the policy, thresholds, component revisions, licences, input contract,
primary metric, minimum improvement, and material-kind regression limits before
the admission run.

### E5 — canonical admission

Run the exact baseline and frozen candidate on the same human-reviewed support
pack. Do not inspect the candidate on admission cases before the pack and policy
hashes are frozen.

The admission gate passes only if the candidate meets the preregistered
improvement and does not regress on any material case kind. Otherwise it fails.
`NOT MEASURED` is replaced only by that recorded result.

### E6 — real-report replay

After admission, replay at least three materially different reports. Keep
uncited claims, fuzzy anchors, unsupported citations, contradictions,
inaccessible sources, and abstentions as separate populations.

IC research is the first private proving ground. It does not change the public
engine contract and it is not a production cutover.

### E7 — arena and operator surfaces

Run arena attacks after the source-bound decision, not as a substitute for it.
Use OpenContracts when human annotation volume justifies an operator surface.
Use Inspect AI only when Groundnut's own runner cannot express or reproduce the
required experiment without duplicating substantial machinery.

## Component map

| Component | Intended contribution | Current state |
|---|---|---|
| Exact and native checks | Presence, numbers, attribution, offsets | Landed |
| Structured navigation | Candidate evidence selection before support | N1 tested; current compact arms rejected |
| AlignScore | Entailment and typed contradiction | Explored; leading complete-label candidate |
| MiniCheck | Binary unsupported signal | Explored |
| LettuceDetect | Paraphrase tolerance and unsupported spans | Explored |
| SummaC | Sentence-pair consistency aggregation | Explored; offline challenger only |
| semchunk | Evidence-window construction | E2A tested; current configuration rejected |
| BGE rerankers | Independent question-to-evidence relevance | E3A tested; v2-m3 is offline challenger |
| Extractive QA | Independent question answerability | E3B tested; leading offline challenger |
| OpenContracts | Human annotation and review | Interchange landed; application optional |
| Inspect AI | Large experiment orchestration | Adoption trigger not met |
| IC arena | Downstream extrapolation attacks | Private experimental consumer |

## Non-negotiable reporting

Every experiment publishes or records:

- case population and exclusions;
- component and model identities;
- licence identities;
- input, configuration, raw-output, and result hashes;
- per-kind confusion and abstention counts;
- failures and missing outputs;
- whether cases are agent-screened, human-reviewed, development, or protected;
- the decision taken, including “do not adopt.”

No agreement between models establishes truth. No missing attack establishes
exoneration. No aggregate score may hide a material failure class.

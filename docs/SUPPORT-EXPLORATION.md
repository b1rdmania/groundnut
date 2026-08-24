# Semantic-support exploration — 18 August 2026

Status: historical exploration evidence, not an admission result.

This is an **agent-screened development result**, not human-adjudicated gold.
It cannot qualify a detector or change the canonical support gate from
`NOT MEASURED`. The 46 groups contain 184 balanced cases: verbatim support,
supported paraphrase, contradiction, and present-but-irrelevant text.

## North star

Given a claim, the question it is meant to answer, and its cited evidence,
Groundnut should produce a source-bound account of whether the evidence:

- supports the claim;
- contradicts the claim;
- is relevant but insufficient; or
- is present in the source but irrelevant to the question.

Groundnut must not turn “the evidence supports this claim” into “the claim is
true.” It is the referee between an AI-written statement and its cited source,
not an oracle. The immediate product test is whether it can stop a confident
research model from attaching a real citation to an inference that citation
does not actually support.

The balanced probe makes four distinctions structural:

| Case | What a trustworthy judge must notice |
|---|---|
| Verbatim support | The words are present and answer the question. |
| Paraphrased support | The words differ but the supported meaning is retained. |
| Contradiction | The evidence materially disagrees with the claim. |
| Present but irrelevant | The words are present but answer a different question. |

Success is not the highest aggregate model score. A candidate must improve
every material case kind—especially present-but-irrelevant evidence—without
silently sacrificing supported claims. Exact matching, learned detectors, and
question relevance may each contribute a signal; Groundnut owns the final
policy, provenance, fail-closed behaviour, and visible disagreement.

## Results

| Method | 3-way accuracy | Macro-F1 | Binary accuracy | Unsupported recall |
|---|---:|---:|---:|---:|
| Exact normalized substring | 25.0% | 0.167 | 50.0% | 50.0% |
| LettuceDetect base ModernBERT | 49.5% | 0.221 | 49.5% | 0.0% |
| LettuceDetect v2 mmBERT base | 48.4% | 0.224 | 52.7% | 8.7% |
| MiniCheck Flan-T5-Large | 45.1% | 0.259 | 65.2% | 43.5% |
| SummaC-ZS, DeBERTa-base MNLI | 43.5% | 0.240 | **66.3%** | **45.7%** |
| AlignScore-base, three-way NLI | **53.8%** | **0.404** | 64.1% | 39.1% |
| AlignScore-base, question-conditioned binary | 44.0% | 0.268 | 50.5% | 21.7% |

The three-way score keeps `contradicted` separate from `insufficient`.
LettuceDetect without its taxonomy head, MiniCheck, and SummaC are binary
detectors, so none can satisfy that contract alone.

## What the case kinds show

| Method | Verbatim | Paraphrase | Contradiction typed | Present irrelevant |
|---|---:|---:|---:|---:|
| Exact | 46/46 | 0/46 | 0/46 | 0/46 |
| Lettuce base | 46/46 | 45/46 | 0/46 | 0/46 |
| Lettuce v2 | 46/46 | 43/46 | 0/46 | 0/46 |
| MiniCheck | 40/46 | 40/46 | 0/46 | 3/46 |
| SummaC-ZS | 46/46 | 34/46 | 0/46 | 0/46 |
| AlignScore NLI | 43/46 | 39/46 | **15/46** | 2/46 |
| AlignScore question-conditioned | 37/46 | 36/46 | 0/46 | **8/46** |

MiniCheck marked 37/46 contradiction mutations as unsupported, but its binary
interface cannot call them contradictions. Its gain is real at the binary
support boundary and insufficient for Groundnut's full account.

SummaC marked 42/46 contradiction mutations as unsupported, including seven
that MiniCheck missed, but it rejected 12/92 supported cases and found no
present-but-irrelevant case. The fixed local CPU run took about 24 minutes and
used about 2 GB resident memory. An MPS attempt was discarded after a confirmed
backend wait before any output artifact was written. SummaC therefore remains
an offline challenger signal, not a default runtime component or semantic
judge.

AlignScore's published three-way NLI head is the strongest complete-label
candidate measured here. The separately preregistered question-conditioned use
of its QA-trained binary head found more irrelevant evidence, but rejected 19
supported cases and cannot type contradictions. The two results are not merged
post hoc into a tuned policy.

## Decision

- Do not adopt any tested detector as Groundnut's semantic judge yet.
- Retain AlignScore NLI as the leading candidate core: it is the first tested
  component to improve the full three-way task materially and type a useful
  number of contradictions.
- Treat question conditioning as a required independent stage. Its 8/46 result
  is still poor, but it is the first material movement on the measured engine
  gap.
- Retain LettuceDetect's paraphrase-tolerance result as evidence for a
  candidate-retrieval or secondary-support signal.
- Retain MiniCheck's stronger binary unsupported signal as a candidate input to
  a Groundnut-owned decision policy, never as the final verdict.
- Retain SummaC only as an optional offline unsupported/contradiction
  challenger. The seven contradictions it caught that MiniCheck missed are
  worth preserving for policy experiments, but its cost and zero relevance
  movement block runtime adoption.
- Prioritize the present-but-irrelevant class: the best result is now 8/46,
  which remains the clearest measured engine gap.
- A later human-adjudicated run must confirm any decision before admission.

Pinned model revisions and complete per-case decisions are recorded in the
private self-hashed exploration artifacts; source documents and generated cases
remain outside the public repository. The public aggregate receipt is
`results/support-exploration-e1-v1-summary.json`. It binds the published
numbers to the private seven-method comparison artifact with SHA-256
`584fb8b2582cc923403fc485861d82158832ec45e7344937b0a670551317c23b`.
The SummaC run artifact has SHA-256
`2843e6a9c22c34d4510f91101943d4f10e3742d62c290494f22730e59e7d45e6`.

## Independent relevance follow-up

The support table above does not cleanly measure relevance. In particular,
contradictory evidence can answer the question while disagreeing with the
claim. E3 therefore uses a separate contract: verbatim support, paraphrase and
contradiction are relevant; present-but-irrelevant is not. The scorer sees the
question and the candidate evidence only. No threshold was selected after the
run.

| Relevance method | ROC-AUC | Average precision | Complete paired groups |
|---|---:|---:|---:|
| Query-token recall | 0.602 | 0.830 | 17/46 |
| BGE reranker base | 0.613 | 0.850 | 23/46 |
| BGE reranker v2-m3 | **0.676** | **0.861** | **27/46** |
| RoBERTa base SQuAD2 answerability | **0.750** | **0.905** | **31/46** |

“Complete” means that all three relevant variants ranked above the irrelevant
variant inside the same source-bound group. v2-m3 improved every pairwise
comparison. Extractive QA improved again, but still failed to order 15 of 46
complete groups. The relevance lane is now correctly typed and replayable; no
tested scorer is admitted. The summary receipt is
`results/relevance-e3-v1-summary.json`.

One private IC report supplied a separate, unlabelled claim/excerpt envelope.
BGE v2-m3 assigned high semantic-relatedness scores to exact anchors and to
ambiguous or failed fuzzy anchors. Related text need not be the quoted text and
need not support the full claim. Relevance is therefore additive to mechanical
anchoring, never a replacement. The aggregate disclosure is
`results/ic-relevance-envelope-v1-summary.json`.

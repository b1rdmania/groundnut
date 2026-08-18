# Semantic-support exploration — 18 August 2026

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
| AlignScore-base, three-way NLI | **53.8%** | **0.404** | 64.1% | 39.1% |
| AlignScore-base, question-conditioned binary | 44.0% | 0.268 | 50.5% | 21.7% |

The three-way score keeps `contradicted` separate from `insufficient`.
LettuceDetect without its taxonomy head and MiniCheck are binary detectors, so
neither can satisfy that contract alone.

## What the case kinds show

| Method | Verbatim | Paraphrase | Contradiction typed | Present irrelevant |
|---|---:|---:|---:|---:|
| Exact | 46/46 | 0/46 | 0/46 | 0/46 |
| Lettuce base | 46/46 | 45/46 | 0/46 | 0/46 |
| Lettuce v2 | 46/46 | 43/46 | 0/46 | 0/46 |
| MiniCheck | 40/46 | 40/46 | 0/46 | 3/46 |
| AlignScore NLI | 43/46 | 39/46 | **15/46** | 2/46 |
| AlignScore question-conditioned | 37/46 | 36/46 | 0/46 | **8/46** |

MiniCheck marked 37/46 contradiction mutations as unsupported, but its binary
interface cannot call them contradictions. Its gain is real at the binary
support boundary and insufficient for Groundnut's full account.

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
- Prioritize the present-but-irrelevant class: the best result is now 8/46,
  which remains the clearest measured engine gap.
- A later human-adjudicated run must confirm any decision before admission.

Pinned model revisions and complete per-case decisions are recorded in the
private self-hashed exploration artifacts; source documents and generated cases
remain outside the public repository.

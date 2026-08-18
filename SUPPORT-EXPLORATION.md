# Semantic-support exploration — 18 August 2026

This is an **agent-screened development result**, not human-adjudicated gold.
It cannot qualify a detector or change the canonical support gate from
`NOT MEASURED`. The 46 groups contain 184 balanced cases: verbatim support,
supported paraphrase, contradiction, and present-but-irrelevant text.

| Method | 3-way accuracy | Macro-F1 | Binary accuracy | Unsupported recall |
|---|---:|---:|---:|---:|
| Exact normalized substring | 25.0% | 0.167 | 50.0% | 50.0% |
| LettuceDetect base ModernBERT | 49.5% | 0.221 | 49.5% | 0.0% |
| LettuceDetect v2 mmBERT base | 48.4% | 0.224 | 52.7% | 8.7% |
| MiniCheck Flan-T5-Large | 45.1% | 0.259 | 65.2% | 43.5% |

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

MiniCheck marked 37/46 contradiction mutations as unsupported, but its binary
interface cannot call them contradictions. Its gain is real at the binary
support boundary and insufficient for Groundnut's full account.

## Decision

- Do not adopt any tested detector as Groundnut's semantic judge.
- Retain LettuceDetect's paraphrase-tolerance result as evidence for a
  candidate-retrieval or secondary-support signal.
- Retain MiniCheck's stronger binary unsupported signal as a candidate input to
  a Groundnut-owned decision policy, never as the final verdict.
- Prioritize the present-but-irrelevant class: every learned method remained at
  0–3 correct out of 46, which is the clearest measured engine gap.
- A later human-adjudicated run must confirm any decision before admission.

Pinned model revisions and complete per-case decisions are recorded in the
private self-hashed exploration artifacts; source documents and generated cases
remain outside the public repository.

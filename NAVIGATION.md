# Structured evidence navigation

**Experiment contract frozen: 18 August 2026.**

Groundnut may use a document's existing structure, or a deterministic derived
index, to choose a small evidence set before semantic support is assessed.
Navigation answers only this question:

> Which source nodes should the next checker inspect?

It does not answer the user's question. It does not assess support,
contradiction, authority, completeness, or truth.

## North star

Select the smallest source-bound evidence set that retains all required
evidence. A smaller context is useful only when evidence recall survives.

The first benchmark therefore reports both sides:

- exact coverage of every node overlapping the expert-anchored answer span;
- selected nodes, irrelevant nodes, context characters, and context ratio;
- abstentions, selector failures, and high-severity evidence misses.

Full injection is the recall ceiling. A compact navigator is not eligible for
adoption merely because it saves tokens; it must meet a separately frozen
recall bar on labelled cases.

## Contracts

`groundnut-navigation-index/v1` binds every node to the exact source hash,
character offsets, text hash, parent/child edges, indexer identity, and index
self-hash. Native source IDs are retained when supplied. Derived or authored
summaries carry explicit provenance.

`groundnut-navigation-selection/v1` binds the question, index, navigator,
configuration, raw selector output, prompt, token counts, selected IDs, status,
and its own self-hash. The only statuses are `selected`, `abstained`, and
`failed`.

`groundnut-navigation-receipt/v1` re-fetches the selected text from the frozen
source. It verifies the source, node, selection, and resulting context hashes.
It never trusts text returned by a selector.

Strict behaviour is structural:

- an unknown or non-selectable node ID fails;
- duplicate IDs or a selection above the frozen limit fail;
- an empty selection abstains;
- a prompt above the frozen budget abstains before a model call;
- there is no first-node, nearest-node, or full-document fallback;
- deterministic tests have no network access.

## Donor mechanisms

Groundnut adopts mechanisms, not donor product claims.

- [TreeDex](https://github.com/alisawuffles/treedex), inspected at
  `cb506162ef9e14eac41ba032d3a21879aa2c8770e`, supplied the useful one-shot
  pattern: expose a compact tree and ask a model for node IDs. Groundnut removes
  answer generation and makes invalid output fail closed.
- [PageIndex](https://github.com/VectifyAI/PageIndex), inspected at
  `ae2a5b49b5411903633faa299201d6ba1769fd2f`, reinforced the vectorless,
  reasoning-over-structure approach. Groundnut does not inherit its benchmark
  claims or unreleased search machinery.
- [LlamaIndex](https://github.com/run-llama/llama_index) provides useful public
  tree-retrieval precedent. It is not a runtime dependency.
- [Docling](https://github.com/docling-project/docling) is a future candidate
  for deriving structure from unstructured files. Native application structure
  remains preferable when it already exists.

The built-in paragraph index is a transparent test fixture and fallback
indexer. It is not claimed to be the best parser.

## N1 development experiment

The first frozen pack contains 100 LegalBench-RAG CUAD cases sampled from
unique, holdout-excluded source documents. Expert answer offsets are mapped to
all overlapping index nodes. The pack seed is `991`; the maximum derived node
size is 3,000 characters.

The deterministic controls establish the problem:

| Navigator | Exact gold coverage | Mean selected nodes | Mean context ratio |
|---|---:|---:|---:|
| Full injection | 100/100 | 189.07 | 98.90% |
| Lexical structure, max 3 | 8/100 | 3.00 | 6.06% |
| TreeDex-style, Qwen3 0.6B | 3/100 | 4.50 when selected | 8.30% when selected |

The lexical arm saves context but loses required evidence in 92 cases. The
TreeDex-style arm selected valid bounded IDs in 24 cases, abstained in 23, and
failed in 53; it covered the exact expert evidence in only three cases. Of the
failures, 51 were unknown or non-selectable IDs. Neither compact arm is
admissible.

The model arm also consumed 876,463 navigation input tokens over 93 invoked
cases. Its largest input-plus-output count was 32,353 under a 32,768-token
context limit. This makes the next experiment concrete: use short model-facing
handles mapped back to content-addressed IDs, and compare native hierarchy with
the flat paragraph index before trying a stronger selector. The public
aggregate is `results/navigation-n1-v1-summary.json`; full case rows and corpus
text are not published.

## Reproduction

The LegalBench-RAG corpus is not redistributed by this repository.

```bash
python scripts/build_navigation_pack.py \
  --seeds /path/to/groundnut-cuad-seeds.jsonl \
  --corpus-root /path/to/corpus \
  --count 100 --sampling-seed 991 \
  --max-node-characters 3000 \
  --output /path/to/navigation-pack-v1.json

python scripts/run_navigation_evaluation.py \
  --pack /path/to/navigation-pack-v1.json \
  --corpus-root /path/to/corpus \
  --lexical-max-nodes 3 \
  --output /path/to/navigation-evaluation-v1.json
```

The optional local Ollama runner is `scripts/run_navigation_ollama.py`. Model
name, immutable revision, context limit, prompt limit, selection limit,
output-token limit, temperature, and seed are recorded in the navigator
identity and result hash.

`scripts/replay_navigation_ollama_result.py` revalidates frozen raw outputs
through the current adapter without another model call. It exists for auditable
metadata corrections and offline replay, not for changing model decisions.

## N2 preregistration — short selector handles

N1 exposed 24-character content IDs to the model and 51 of 53 failures were
unknown or non-selectable IDs. N2 keeps those IDs in every canonical receipt
but replaces them in the model-facing tree with deterministic source-order
handles (`n0001`, `n0002`, and so on). Valid handles resolve back to the exact
content IDs before evidence is fetched. Unknown, duplicate, excessive, and
non-selectable handles fail closed.

N2 reuses the identical 100 cases, Qwen3 0.6B model blob, maximum five nodes,
100,000-character prompt limit, 128-token output limit, temperature zero and
seed 991. It changes only the surface schema, prompt and selector identity.
The preregistered interface target is at most five unknown-handle failures, at
least 24 valid selections, and no regression from N1's 3/100 exact coverage.
Meeting that target does not admit the navigator; it only establishes whether
short handles fixed the measured copying failure.

N2 passed that narrow target: unknown identities fell from 51 to 4, valid
selections rose from 24 to 44, exact coverage rose from 3/100 to 8/100, and
navigation input fell from 876,463 to 758,645 tokens. It remains rejected.
Forty-three failures were valid handles resolving to non-selectable structural
nodes.

N3 therefore leaves structural rows visible but assigns handles only to
selectable evidence nodes. It reuses every other N2 input. The preregistered
interface target is zero structural-node failures, at most five unknown-handle
failures, at least 44 valid selections, and at least 8/100 exact coverage.

N3 removed the measured structural-addressing failure and improved evidence
coverage, but it did not pass every preregistered interface target. Structural
node failures fell from 43 to zero, valid selections rose from 44 to 79, and
exact coverage rose from 8/100 to 13/100. The model produced unknown handles in
six cases, one above the frozen maximum. It abstained in 12 cases and failed in
nine. When it selected, it returned a mean 4.92 nodes, of which 4.76 were
irrelevant, using 6.95% of source context.

The result keeps selectable-only handles as the safer experimental interface,
not as an admitted navigator. Thirteen percent exact coverage is unsafe. The
next model comparison must use this fixed interface and the identical frozen
pack; it must not spend another run tuning handles against these same cases.
The N1-to-N3 aggregate is
`results/navigation-interface-n1-n3-v1-summary.json`.

## N4 preregistration — stronger selector, frozen interface

N4 tests model capacity rather than changing the navigation contract again.
It replaces Qwen3 0.6B with the Apache-2.0 Qwen3 8B model blob
`sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`.
The 100-case pack, selectable-only handle surface, prompt, five-node limit,
100,000-character prompt limit, 32,768-token context, 128-token output limit,
temperature zero and seed 991 remain fixed.

Before the first N4 model call, a result is worth further selector work only if
all of these development targets hold:

- exact coverage is at least 26/100, double N3's 13/100;
- mean required-node recall is at least 0.26;
- at least 75 cases return a valid bounded selection;
- structural-node failures remain zero;
- unknown-handle failures are at most five; and
- mean context ratio when selected is at most 10%.

These targets test material movement under a stronger model. They are not an
admission bar. A passing N4 selector still cannot replace full evidence without
a separately preregistered safety threshold on evidence it has not shaped.
The local run uses one worker so concurrent requests cannot change the resource
envelope.

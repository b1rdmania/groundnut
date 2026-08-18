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
  --count 100 --unique-sources --sampling-seed 991 \
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

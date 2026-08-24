# Findings — 17 August 2026

Status: legacy compatibility evidence for the original CUAD extractor, not the
IC product acceptance record.

A measurement session. **No model was called** — every number here comes from
cached predictions or static files, so nothing below establishes current model
behaviour. It establishes what the stored artefacts say, and where the harness
is measuring the wrong thing.

Status marks are the confidence level, not the prose around them:

| Mark | Meaning |
|---|---|
| `VERIFIED` | A command was run or a file read. Reproducible from this repo. |
| `ESTIMATED` | Arithmetic, or a source read but not independently checked. |
| `UNTESTED` | A hypothesis. No evidence either way. |

**Later independent review found additional errors in the first correction
pass.** They are corrected in §§1–3; the original measurements remain visible
where useful, but their invalid interpretations do not.

---

## 1. The grounding number measures the filter, not the model — `VERIFIED`

The claim "every quote is verbatim in its source" was being supported with a
1.0000 grounding score across thousands of predictions. That score is an
artefact.

`pipeline/extract.py::filter_verbatim()` drops any span that is not an exact
substring of its source **before findings are recorded**:

```python
def filter_verbatim(findings, source_text):
    """Drop any span that is not an exact substring of the source it came from."""
    kept = [s for s in spans if s in source_text]
```

On a filtered run, grounding is 1.0000 **by construction**. `LOG.md` said as
much in cycle 7 — *"grounding 1.0000 (filter working)"* — and it was read past.

| Run | Filter | Normalised judge | Exact substring |
|---|---|---|---|
| Filtered pipeline runs | Yes | 1.0000 | 1.0000 by construction |
| `runs/predictions-claude-opus-4.8-agent` | No | 0.9744 | **0.9283** |
| `runs/predictions-claude-sonnet-5-agent` | No | 0.9665 | **0.9070** |

**Two claims. Never merge them.**

- **Architectural** — the pipeline cannot emit an ungrounded quote. Unmatched
  spans are dropped at extraction. A design guarantee, *not* evidence about the
  model.
- **Empirical** — unfiltered agent outputs are grounded **~97% under the
  normalised judge**, but exactly verbatim only **~91–93%** of the time. The
  judge folds case, whitespace, quotes, dashes, and non-breaking spaces.

**Caveat:** both rates rest on two agent runs `LOG.md` calls *"indicative, not
API-reproducible"* — whole-document context, no temperature pinning, non-API
protocol. Neither has been established under a reproducible API run.

**Framing:** this is a *provenance* guarantee, not a *truth* guarantee.
Retrieval can be incomplete, a source can be wrong, and a correctly-quoted span
can still be the wrong span.

---

## 2. The chunker fires on two-thirds of the corpus — `VERIFIED`

The most actionable finding here, and the cheapest to act on.

| Fact | Value |
|---|---|
| `CHUNK_CHARS` in `pipeline/chunking.py` | 20,000 |
| Median contract | 33,143 chars |
| p90 / max contract | 122,054 / 338,211 (nearest-rank p90) |
| **Contracts that get chunked** | **347/510 (68%)** |
| **Of the dev-80 working set** | **56/80 (70%)** |
| Chunks per contract | mean **3.18**, max **18** |

Cycle 7 observed 0.4067 High-severity precision on a 45-document chunked API
run and 0.5721 on an 80-document whole-document agent run of the same named
model. That is **not a controlled chunking experiment**: protocol, filtering,
temperature control, and document coverage also changed. On the shared
45-document cohort the gap remains (0.4067 vs 0.5606), making chunking a strong
hypothesis rather than an established cause.

**It is not a safety net. It is the common path for 70% of the eval set.** Run
the same backend and cohort with only the threshold changed before claiming
how much that costs.

**Fix:** raise `CHUNK_CHARS` above 338,211 and it never fires on this corpus.
Cost per request rises accordingly.

**Do not delete the chunker.** `spec.md` §4 requires a path for contracts longer
than the model context, and `LOG.md` records that the merge was
"implemented and unit-tested but never exercised against a real contract" —
its behaviour on the largest documents is unverified either way. Verify the
merge path before relying on any setting.

---

## 3. Criterion 1 may be measuring the wrong thing — `VERIFIED`

Matcher sweep on cached predictions, dev-80 working set, against
`runs/predictions-claude-opus-4.8-agent`. The baseline reproduces cycle 7's
logged 0.4916 exactly, which validates the sweep.

| Matcher | macro-F1 | Precision | Recall | vs 0.55 bar |
|---|---|---|---|---|
| `jaccard@0.5` (current) | 0.4916 | 0.630 | 0.381 | FAIL |
| `jaccard@0.3` | 0.5372 | 0.672 | 0.421 | FAIL |
| **`containment@0.5`** | **0.6415** | **0.824** | **0.631** | **PASS** |
| `containment@0.8` | 0.5854 | 0.798 | 0.550 | PASS |
| `gold-covered@0.8` | 0.5310 | 0.725 | 0.500 | FAIL |

The current matcher (`harness/score.py`) is symmetric token-set Jaccard at 0.5.
It may penalise a correct extraction for choosing different span boundaries,
but the table above does not establish that.

**Independent-review correction:** the scorer matches predictions and gold
spans independently rather than one-to-one. Under containment, 381 predictions
match multiple gold spans and 282 gold spans match multiple predictions.
Maximum one-to-one matching changes:

| Matcher | macro-F1 | Precision | Recall |
|---|---|---|---|
| `jaccard@0.5`, one-to-one | 0.4832 | 0.623 | 0.373 |
| `containment@0.5`, one-to-one | **0.5661** | 0.791 | 0.474 |

The earlier precision argument was also mathematically wrong. Applied to a
fixed prediction set, a more permissive matcher can only reclassify false
positives as true positives, so measured precision must rise or stay flat.
That increase says nothing about whether a human would accept the new matches.
Containment remains a candidate, not a validated replacement.

> ⚠️ **This has not been adopted, and should not be adopted casually.**
>
> An eval whose owner swaps the metric until it passes has destroyed the only
> thing that made it worth having. Two conditions before any change:
>
> 1. **The 0.55 bar was calibrated under Jaccard and cannot be inherited.**
>    Re-derive it for containment **and write it down before re-scoring**.
>    Passing an old bar with a new metric is not a result.
> 2. **Holdout is unspent** — correctly, because nothing has passed dev. It is
>    the one-shot honest test once a bar exists.

---

## 4. There is no retrieval step — `VERIFIED`

`pipeline/chunking.py::chunk_text()` returns **every** chunk. Nothing ranks or
selects: a grep of `pipeline/` for `rank|score|top_k|select|retriev|embed`
returns zero hits.

This was checked because a retrieval benchmark was proposed for this repo. It
does not apply — Precision@k and Recall@k have nothing to attach to, and
adopting one would mean building a retrieval layer the engine does not have
purely to be scoreable.

`goal.md` already defines the better-fitting harness: macro-F1 over the 41
categories, a fixed 80-doc stratified working set (every category ≥5 positives),
dev-full 306, rate-limited holdout, and a bar set against published baselines.

**Scope correction — 17 August 2026.** This conclusion applies to retrieval or
replacement extraction benchmarks for the compatibility pipeline. Groundnut's
canonical remit now includes semantic claim support, which the 41-category
span-extraction gate does not measure. The new four-cell support benchmark is a
separate product measurement, not a substitute score for the old extractor.
Both gates and the unchanged historical failure are retained. Read `../GATES.md`.

---

## 5. A span-accuracy floor, heavily confounded — `ESTIMATED`

31.0% of cached quotes overlap an annotated span in an external span-annotated
derivative of the same corpus (940/3,037), against a ~10% chance baseline
(annotations cover mean 9.8% / median 9.1% of document characters). Roughly 3×
chance.

**A floor, not a score.** That external set annotates ~13.5 spans per document —
a subset of the 41 categories — so a correct quote for an unannotated category
scores as a miss. A clean number needs category alignment, which was not
attempted.

---

## 6. Reproducing all of this

All offline. None of it calls a model.

```bash
# the corpus is not redistributed — rebuild it first
python3 scripts/fetch_corpus.py --cuad /path/to/CUADv1.json
python3 harness/probe.py                    # regenerates eval/probe, seed 991

python3 -m pytest tests/ -q
bash harness/gate.sh dev
bash harness/gate.sh dev --pred-root runs/predictions-claude-opus-4.8-agent
```

**The matcher sweep and the chunking census were ad-hoc and are not committed.**
The sweep imports `harness/score.py`, monkeypatches `score.match`, and re-runs
`score_split` against the dev-80 working set.

> ⚠️ **The trap.** Score against the full 306-doc gold instead of the 80-doc
> working set and macro-F1 collapses to ~0.21, recall to ~0.11, because most
> gold documents have no predictions in a given run. Cycle 7 flags the identical
> trap ("macro-F1 0.3008 is a coverage artifact — DO NOT cite"). Filter gold
> through `eval/dev/working-set.json`.

---

## 7. What to attack

Ordered by how much damage a wrong answer does.

1. **Repair the scorer under an audited evaluator change.** Add one-to-one
   matching and regression tests before comparing Jaccard and containment.
2. **Human-audit containment-only dev matches.** Aggregate precision cannot
   decide whether they are legitimate boundary variants. Do not inspect or
   spend holdout while designing the rule.
3. **Run a controlled chunking comparison.** Same backend, prompt, cohort, and
   temperature; change only the chunk threshold. Exercise the largest-contract
   merge path first.
4. **Reproduce both empirical grounding rates through an API:** exact substring
   and the separately named normalised judge.
5. **Corpus round-trip — completed.** An isolated rebuild produced all 510 files
   byte-for-byte, and `fetch_corpus.py` now enforces `sha256_raw` from the
   manifest with a tamper regression test.
6. **Re-derive the 31% figure** and decide whether category alignment rescues it
   or it should be dropped as uninformative.

---

## 8. Known limitation in the repo's own integrity controls

`.claude/settings.json` denies Edit/Write on `harness/**`, `eval/**`, `goal.md`
and `spec.md`, and denies reading the private answers directory — so that an
agent being evaluated cannot touch its own judge or see the answers.

**Those denies gate the Edit/Write tools, not shell commands.** `Bash(sed *)`,
`Bash(python3 *)` and similar are not on the deny list, so the protection is one
shell command deep. During this session `harness/gate.py` and `harness/score.py`
were edited via `sed` — docstring-only changes, no logic touched, gate output
byte-identical, all confirmable from the diff — but the hole is real regardless
of intent.

Close it before running another cycle.

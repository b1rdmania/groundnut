# Claim ledger

The claim ledger is the reader-facing output of a canonical run over a
research report. Every prose unit in the report lands in exactly one of three
buckets:

| bucket | meaning |
|---|---|
| `excerpt_found` | the cited excerpt was found byte-exactly or through a named mechanical normalisation in the source snapshot |
| `citation_unconfirmed` | evidence is declared but the excerpt was `excerpt_not_found`, the `evidence_window_incomplete`, the quote was ambiguous, no excerpt was supplied, the source was unavailable, or a preserved bare locator was `unresolvable_source` |
| `own_reasoning` | no citation, or declared analysis; split into `declared`, `numeric` (carries a number, %, currency, or multiplier), `narrative` |

`excerpt_found` means the quoted words are in the snapshot. It is not a
statement that the claim is true, or that the source supports the claim. The
semantic support status rides alongside every cited row and is `insufficient`
for all of them until a support detector passes the admission gate.

`excerpt_not_found` is emitted only when the snapshot declares its searchable
evidence window complete. A failed search over a truncated, legacy, or otherwise
unknown window is `evidence_window_incomplete`. Ledger rows retain the window
hash and truncation state so the distinction survives into IC JSON and Markdown
surfaces. See [Evidence windows](./EVIDENCE-WINDOWS.md).

A confidential document, physical record or filing may have a usable locator
but no public URL. Groundnut preserves that bare locator and records
`citation_unconfirmed:unresolvable_source`. It counts as declared evidence for
citation coverage, but not as a resolvable or accessible source. No mechanical
or semantic support check is claimed.

`own_reasoning:numeric` is where LLM extrapolation in a diligence report tends
to live — derived market sizes, paybacks, unit economics. The split is
mechanical and is a reading aid, not a judgement.

## Declared analysis and the undeclared-numerics gate

A writer owns its arithmetic by marking the sentence:

```markdown
At a $26,000 price the payback condition requires V > $184,000 per year. <!-- ic-own: derived from cited price and switching cost -->
```

Any comment class listed in the profile's `declared_analysis_classes`
(`ic-own` in the IC profile) works; the marker binds to the sentence it
follows, not the whole paragraph. Declared units land in
`own_reasoning:declared`.

`python3 -m groundnut.ic_loop --gate-undeclared-numerics` then turns the
remaining `own_reasoning:numeric` count into a build gate: exit 1, with every
offending unit listed. The fix is to cite the number or declare it — never to
delete it. This converts extrapolation from something detected after the fact
into something a report cannot ship undeclared.

The gate does not spend a writer fix cycle on tightly defined document
furniture: bare list ordinals, standalone dates, generated-report bylines and
data-cutoff lines, plus section and phase coordinates, remain visible as
narrative ledger units but are not numeric claims. Removing a document
coordinate does not exempt other numbers in the same sentence: `Section 6
reports $4.2M` still enters the gate. A dated factual sentence (for example, a
founding year or forecast) also still enters the numeric gate.

An intentional exception requires `--waiver waiver.json`. A waiver records a
non-empty approver identity and reason and binds the exact artifact hash,
ledger hash, and complete failing unit-id set. Groundnut writes the validated
waiver and its hash into `gate.json`. A changed report or ledger invalidates
the waiver. The record provides attribution, not reviewer independence: the
approver may also have authored or operated the run.

The gate has four outcomes: `clear`, `failed`, `waived`, and `indeterminate`.
An empty or malformed claim population is `indeterminate`, never `clear`, and
cannot be waived. In particular, unclosed Markdown frontmatter or code fences
are reported as population anomalies rather than silently hiding the rest of
the artifact.

Annotation combinations are observations, not generic engine verdicts. Each
ledger row carries its detected `annotations` and any `annotation_conflicts`.
For example, a citation combined with a declared-analysis marker is surfaced
as `citation_and_declared_analysis`; a consuming product decides whether that
combination is allowed by its writing contract.

## Run it

One command, the IC loop:

```bash
python3 -m groundnut.ic_loop --report research-report.md --out groundnut/ --title "Acme claim ledger"
```

It fetches and snapshots every cited source once (`--replay-only` refuses the
network), runs the canonical check with `domains/ic_research.json` and
`profiles/ic-research-pipeline.json`, and writes `request.json`, `run.json`,
`ledger.json`, `ledger.md`, `gate.json`, `input/report.md`, `snapshots/`. The
bundled request uses logical relative paths, so separate replay directories
produce the same request identity and do not disclose an operator's local home
path. The research pipeline calls this as its Phase 4.5. The two underlying
steps:

```bash
python3 -m groundnut.canonical_cli --request request.json --out run.json
python3 -m groundnut.ledger_cli \
  --run run.json \
  --artifact research-report.md \
  --profile artifact-profile.json \
  --out ledger.json \
  --markdown ledger.md
```

The artifact must be the same markdown the run checked; the ledger binds the
run hash and the artifact hash and fails if either differs. The profile must
be the one the run used; pipelines that emit `ic-source-quote` comments set
`evidence_comment_prefix` to `ic-source`.

## Live run, 23 August

Same report, empty snapshot directory, `snapshot_preferred`: 67 seconds, 74 of
85 sources fetched and archived, 11 failed (5 × HTTP 403, 2 × 404, one PDF,
one 999, one redirect loop). Ledger 63 / 42 / 296, identical to the 17 August
replay. HTTPS fetches use a certifi CA bundle when one is installed, because
some Python builds have no system trust store and would otherwise report every
source as unreachable.

PDF sources are read through their text layer (pypdf); scanned PDFs with no
text layer stay `pdf_unsupported`. With that, the Citeline investor-day PDF
resolved and its quotation was found: 64 / 41 / 296 on the 23 August rerun.
Two more sources happened to fail that run (live sites vary between fetches);
the snapshot directory is what makes a run reproducible, not the internet.

## Segmentation

Every count depends on the segmenter, whose identity is hashed into the
ledger. Segmenter v6 excludes narrowly defined section and phase coordinates
from the numeric gate without hiding other quantities in the same sentence.
Segmenter v4 admits non-header table cells as units; frontmatter,
headings, horizontal rules, table headers/delimiters and fenced code remain
named exclusions. Prose lines split into sentences; a sentence with an HTTP
citation is one cited unit per citation; uncited sentences in the same
paragraph are their own units; list items split the same way; every non-empty
prose sentence is retained. Segmenter v3 removed the previous eight-word floor
because short deck-style claims such as `Market: $4.2B by 2030.` must enter the
numeric gate.

`ledger.json.population` prints included and excluded physical-line counts and
any structural anomalies. This is line/region accounting, not a promise to be
a lossless Markdown renderer.

Known coarseness: a sentence with two citations appears twice, once per
citation.

The 466-unit v0.1.0a2 RxClarity beta excluded table rows. Segmenter v4 measured
the same artifact at 567 units: 105 citation-bearing units (18.5%), 462 own
reasoning, and 125 undeclared numerics. Admitting 13 table-body lines added 101
units and 37 undeclared numerics. The apparent coverage decline is the correct
effect of measuring a larger population, not a regression in cited content.

## First real ledger

RxClarity research report (private), 22 August 2026, exact baseline detector,
replay from the 17 August snapshots, segmenter v2: 401 units — 63 excerpts
found, 42 citations unconfirmed (11 not found, 13 ambiguous, 8 no excerpt, 10
source unavailable), 296 own reasoning (80 numeric, 216 narrative). Segmenter
v1, which kept whole cited paragraphs as one unit, reported 329 / 63 / 42 /
224; the difference is the uncited sentences that v1 hid inside cited
paragraphs. Private rows stay
in the IC run directory; only these aggregates are public.

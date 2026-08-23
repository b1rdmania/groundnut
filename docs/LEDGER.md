# Claim ledger

The claim ledger is the reader-facing output of a canonical run over a
research report. Every prose unit in the report lands in exactly one of three
buckets:

| bucket | meaning |
|---|---|
| `cited_verified` | the cited excerpt was found verbatim in the source snapshot |
| `cited_drifted` | a citation exists but the excerpt was `quote_not_found`, `quote_ambiguous`, had `no_excerpt`, or the source was `source_unavailable` |
| `own_reasoning` | no citation, or declared analysis; split into `declared`, `numeric` (carries a number, %, currency, or multiplier), `narrative` |

`cited_verified` means the quoted words are in the snapshot. It is not a
statement that the claim is true, or that the source supports the claim. The
semantic support status rides alongside every cited row and is `insufficient`
for all of them until a support detector passes the admission gate.

`own_reasoning:numeric` is where LLM extrapolation in a diligence report tends
to live — derived market sizes, paybacks, unit economics. The split is
mechanical and is a reading aid, not a judgement.

## Run it

One command, the IC loop:

```bash
python3 -m groundnut.ic_loop --report research-report.md --out groundnut/ --title "Acme claim ledger"
```

It fetches and snapshots every cited source once (`--replay-only` refuses the
network), runs the canonical check with `domains/ic_research.json` and
`profiles/ic-research-pipeline.json`, and writes `request.json`, `run.json`,
`ledger.json`, `ledger.md`, `snapshots/`. The research pipeline calls this as
its Phase 4.5. The two underlying steps:

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
ledger. Rules: frontmatter, headings, horizontal rules, table rows, and fenced
code are not claims; prose lines split into sentences; a sentence with an
HTTP citation is one cited unit per citation; uncited sentences in the same
paragraph are their own units; list items split the same way; units under
eight words are dropped.

Known coarseness: a sentence with two citations appears twice, once per
citation.

## First real ledger

RxClarity research report (private), 22 August 2026, exact baseline detector,
replay from the 17 August snapshots, segmenter v2: 401 units — 63 cited and
verified, 42 cited but drifted (11 not found, 13 ambiguous, 8 no excerpt, 10
source unavailable), 296 own reasoning (80 numeric, 216 narrative). Segmenter
v1, which kept whole cited paragraphs as one unit, reported 329 / 63 / 42 /
224; the difference is the uncited sentences that v1 hid inside cited
paragraphs. Private rows stay
in the IC run directory; only these aggregates are public.

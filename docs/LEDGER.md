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

## Segmentation

Every count depends on the segmenter, whose identity is hashed into the
ledger. Rules: frontmatter, headings, horizontal rules, table rows, and fenced
code are not claims; a line with an HTTP citation is one cited unit per
citation (the artifact segmenter's rule); other prose lines split into
sentences; list items are one unit each; units under eight words are dropped.

Known coarseness: a cited line carries its whole line as the unit text, so a
paragraph with two citations appears twice, and uncited sentences inside a
cited paragraph are not separated out.

## First real ledger

RxClarity research report (private), 22 August 2026, exact baseline detector,
replay from the 17 August snapshots: 329 units — 63 cited and verified, 42
cited but drifted (11 not found, 13 ambiguous, 8 no excerpt, 10 source
unavailable), 224 own reasoning (66 numeric, 158 narrative). Private rows stay
in the IC run directory; only these aggregates are public.

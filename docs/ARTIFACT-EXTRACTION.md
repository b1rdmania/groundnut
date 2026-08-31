# Artifact extraction admission

Groundnut's canonical artifact extractor accepts Markdown, rendered HTML and
structured memo JSON. The frozen admission below measures segmenter version 5,
which emits every eligible prose sentence
and table cell, including uncited statements. Citations, excerpts, locators,
questions, declared analysis and canonical provenance classes remain attached
when the artifact supplies them; the extractor does not invent missing
evidence.

Segmenter version 5 preserves a bare locator even when the source has no URL,
uses nesting-aware HTML exclusions and provenance, and binds expected claim
locations into the frozen admission result.

## Measured version 5 contract

The frozen public conformance pack is
[`evaluation/artifact_extraction/v1/benchmark.json`](../evaluation/artifact_extraction/v1/benchmark.json).
It contains 20 unique, sanitized claims spanning the three formats and seven
claim categories: cited quotes, cited locators, declared analysis, typed
unsourced claims, uncited numerics, table labels and table numerics.

The checked-in admission receipt is
[`results/artifact-extraction-admission-v1.json`](../results/artifact-extraction-admission-v1.json).
On this pack, precision, recall, field accuracy and location accuracy are all
`1.000`. Expected locations are labelled alongside the other claim fields;
the fixture and profile bytes are hash-frozen before evaluation, and the
evaluator rejects changed inputs.

This is a supported-syntax conformance result. It is deliberately small and
does not establish representative extraction accuracy for arbitrary documents,
renderers or malformed markup. New real-world failures must become sanitized,
labelled cases before the quality claim expands.

## Inclusion and exclusion rules

- Structured memo JSON emits one claim for every configured claims-array row.
- Markdown emits eligible prose sentences and table cells. Frontmatter,
  headings, horizontal rules, fenced code and table separator rows remain
  excluded by the Markdown population contract.
- Rendered HTML emits eligible normalized sentences and table cells. Generic
  script, style, title, navigation, header, footer, heading and table-header
  chrome is excluded. Profile exclusions and provenance annotations inherit
  through nested containers without leaking into following siblings.
- Host-specific bibliography or renderer chrome must use the profile's named
  ignored classes or attributes. Host-specific provenance and declared-analysis
  vocabulary is configuration, not Groundnut engine logic.
- Locations identify the structured row, Markdown line or normalized HTML block
  that produced the claim. HTML locations are not physical source-file line
  numbers.

Reproduce the public result offline:

```bash
python3.12 -m groundnut.extraction_admission \
  --benchmark evaluation/artifact_extraction/v1/benchmark.json \
  --out results/artifact-extraction-admission-v1.json \
  --markdown results/artifact-extraction-admission-v1.md
```

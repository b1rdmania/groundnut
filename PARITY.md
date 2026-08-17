# Downstream adapter parity contract

This contract is frozen for any future host adapter. It does not make an
adapter a current priority. If a downstream product is eventually ported, the
adapter does not replace its existing path until the fixture matrix below
passes against both implementations.

## Compared artifact

Both paths must map their result into `groundnut-analysis/v1`, after which
`groundnut.parity.semantic_projection` is byte-compared as canonical JSON. The
projection includes the exact 18-category playbook identity, source hash and
length, segmentation count, fail-closed coverage, findings, severities, quotes,
and exact anchor properties and offsets. Array order remains significant.

The only exclusions are printed in every parity comparison:

- evidence disclosure/status and manifest hash, which the legacy path never
  produced;
- host-local source identifiers, including those repeated inside anchors.

Timestamps, database UUIDs, audit-row IDs, user IDs, model latency/token usage,
and UI-only ordering must stay outside the mapped analysis artifact. No new
exclusion may be added in response to a failing fixture: change this contract
and review the rationale first. The comparator rejects unknown fields, so a
future schema addition cannot disappear from parity silently.

## Fixture matrix

Parity must cover, before adapter implementation can replace anything:

1. one synthetic source for every one of the 18 deployed categories;
2. no-finding, multi-finding, duplicate-quote, and multi-segment sources;
3. invalid JSON, missing category acknowledgements, unknown categories, and a
   failed segment, all of which must remain incomplete rather than clear;
4. repeated exact quotes, punctuation/whitespace variants, and merged findings;
5. document-type classification and category batching once those pure
   deployment functions have been extracted.

Each path receives the same normalized source bytes, category order,
segmentation, and replayed model responses. No live model and no network are
allowed. The default M&A prompt bytes are compared separately because prompt
parity can change outputs even when the result schema is unchanged.

## Release rule

The legacy and Groundnut-backed paths run side by side until every fixture has
identical semantic bytes and the comparison hashes are recorded. Only then may
the host switch its default. The old path is removed in a later change, after
deployment observation; parity passing does not authorize deletion by itself.

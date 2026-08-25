# Evidence-window contract

**Frozen:** 25 August 2026  
**Snapshot schema:** `groundnut-source-snapshot/v2`

Groundnut verifies excerpts only against the normalized text it captured. A
failed search is an `excerpt_not_found` result only when that searchable window
is known complete. When capture was truncated, or a legacy/host producer cannot
establish completeness, the honest result is `evidence_window_incomplete`.

## Window object

Every successful v2 snapshot carries `evidence_window`:

```json
{
  "schema": "groundnut-evidence-window/v1",
  "original_bytes": 1200,
  "original_characters": 1180,
  "captured_bytes": 740,
  "captured_characters": 735,
  "truncation": "complete",
  "extraction_method": "html.parser-visible-text/v1",
  "text_sha256": "...",
  "sha256": "..."
}
```

`original_*` describes the acquired representation before text extraction and
is nullable when the producer cannot know it. `captured_*` and `text_sha256`
describe the exact normalized text searched by verification. Extraction can
legitimately make captured text shorter than the original without implying
truncation; `truncation` is an explicit producer statement with values
`complete`, `truncated`, `unknown`, `empty`, or `sparse`. `empty` means text
normalization yielded no searchable characters. `sparse` is the built-in HTML
producer's fail-closed classification for less than 1,024 visible characters
from a response of at least 4,096 bytes. Neither state permits Groundnut to
conclude that a missing excerpt was searched-and-absent.

The object is invalid unless captured lengths and `text_sha256` match the
snapshot text. Known lengths must be non-negative. A producer may declare
`complete` only when it knows the entire acquired representation was processed
and produced a usable searchable window. Existing v2 snapshots that recorded
an empty or structurally sparse HTML window as `complete` are reclassified on
read without rewriting the frozen snapshot.

## Built-in producers

- files: complete UTF-8 decode with replacement, original byte and character
  lengths known;
- HTTP text: complete response decode, original byte and character lengths
  known;
- HTTP HTML: complete response decode followed by visible-text normalization;
- HTTP PDF: original byte length known, original character length unknown;
  truncation is explicit when the PDF page count exceeds the configured page
  extraction limit.

## Replay compatibility

V2 snapshots preserve the exact window object. Loading a successful v1
snapshot constructs a hash-bound window over its stored text with
`truncation: unknown` and `extraction_method: legacy-snapshot/v1`. This retains
replay access without inventing a historical completeness claim. Consequently,
a missing excerpt in a v1 snapshot becomes `evidence_window_incomplete`, while
an excerpt found inside that snapshot remains `excerpt_found`.

Failure snapshots remain `groundnut-source-failure-snapshot/v1`; they contain
no searchable evidence window.

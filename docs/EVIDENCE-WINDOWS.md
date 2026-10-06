# Evidence-window contract

**Frozen:** 31 August 2026

**Snapshot schema:** `groundnut-source-snapshot/v3`

Groundnut verifies excerpts only against the text it captured. A
failed search is an `excerpt_not_found` result only when that searchable window
is known complete. When capture was truncated, or a legacy/host producer cannot
establish completeness, the honest result is `evidence_window_incomplete`.

## Window object

Every successful v2 or v3 snapshot carries `evidence_window`. New built-in HTTP
captures use v2, which adds the producer identity while retaining the v1 text
and completeness fields:

```json
{
  "schema": "groundnut-evidence-window/v2",
  "original_bytes": 1200,
  "original_characters": 1180,
  "captured_bytes": 740,
  "captured_characters": 735,
  "truncation": "complete",
  "extraction_method": "html.parser-visible-text/v2:charset=utf-8",
  "extractor": {
    "name": "html.parser-visible-text",
    "version": "2",
    "parameters": {"charset": "utf-8", "max_characters": 8388608}
  },
  "extractor_library": null,
  "runtime": {"name": "python", "version": "3.12.11"},
  "text_sha256": "...",
  "sha256": "..."
}
```

`original_*` describes the acquired representation before text extraction and
is nullable when the producer cannot know it. `captured_*` and `text_sha256`
describe the exact stored text searched by verification. Extraction can
legitimately make captured text shorter than the original without implying
truncation; `truncation` is an explicit producer statement with values
`complete`, `truncated`, `unknown`, `empty`, `sparse`, or `hollow`. `empty` means text
normalization yielded no searchable characters. `sparse` is the built-in HTML
producer's fail-closed classification for less than 1,024 visible characters
from a response of at least 4,096 bytes. The JSON producer has its own bounds,
described under [JSON leaf text](#json-leaf-text). Neither state permits
Groundnut to conclude that a missing excerpt was searched-and-absent.

`hollow` is a high-confidence unusable observation: a bounded CAPTCHA/human
check, access-denied page, JavaScript-required shell, Cloudflare/browser check,
rate-limit response, subscription/sign-in wall, or cookie-only wall. Detection
is performed once during built-in HTML extraction and is bounded by visible
text length so a genuine long article mentioning Cloudflare or cookies remains
`complete`. A hollow window is indeterminate, is never a successful evidence
observation, and cannot be upgraded to claim support even when challenge-page
text matches an excerpt.

The object is invalid unless captured lengths and `text_sha256` match the
snapshot text. Known lengths must be non-negative. A producer may declare
`complete` only when it knows the entire acquired representation was processed
and produced a usable searchable window. Existing v2 snapshots that recorded
an empty or structurally sparse HTML window as `complete` are reclassified on
read without rewriting the frozen snapshot.

The v2 producer identity is part of the evidence-window hash. `extractor`
names the extraction contract and its parameters. `extractor_library` records
the installed third-party package and version when one produces the text
(`pypdf` for PDF); standard-library producers use `null`. `runtime` records the
Python version. These fields explain extraction drift; they do not claim that
different versions reproduce the same text.

## Built-in producers

- files: complete UTF-8 decode with replacement, original byte and character
  lengths known;
- HTTP text: complete response decode, original byte and character lengths
  known;
- HTTP HTML: complete response decode followed by visible-text normalization;
- HTTP PDF: original byte length known, original character length unknown;
  truncation is explicit when the PDF page count exceeds the configured page
  extraction limit. Its v2 identity records the installed pypdf version.
- HTTP JSON (`application/json` exactly): complete response decode, strict
  parse, then `json-leaf-text/v1` rendering. Original byte and character
  lengths describe the decoded JSON body, as for other text.

## JSON leaf text

Several primary records are published only through JSON APIs (for example
the ClinicalTrials.gov v2 API, the bioRxiv/medRxiv details API and Europe PMC
REST search), while their HTML pages are script shells or refuse automated
reads. Raw JSON is a poor search window: string escapes and key syntax sit
between a quoted value and its text. `json-leaf-text/v1` renders the parsed
document as searchable text instead.

```text
extraction_method: json-leaf-text/v1:charset=utf-8
extractor: {"name": "json-leaf-text", "version": "1",
            "parameters": {"charset": "utf-8", "max_characters": 8388608,
                           "max_depth": 64, "max_values": 1000000}}
extractor_library: null
```

Every leaf becomes one line, `<path>: <value>`, in document order. A leaf is a
string, number, `true`, `false`, `null`, or an empty object or array. Lines are
joined with `\n` and there is no trailing newline.

```text
protocolSection.statusModule.overallStatus: COMPLETED
protocolSection.designModule.phases[0]: PHASE2
protocolSection.designModule.enrollmentInfo.count: 47079
resultsSection.outcomeMeasuresModule.outcomeMeasures[0].paramValue: 243.40
derivedSection.conditionBrowseModule.meshes: []
hasResults: true
["@context"]: https://schema.org
```

Path syntax:

- an object key matching `[A-Za-z_][A-Za-z0-9_-]*` is a plain name, joined to
  its parent with `.` (no leading dot at the root);
- every other key, including keys containing `.`, `[`, `]`, `"`, `:`,
  whitespace or non-ASCII characters, keys starting with a digit, and the empty
  key, is written as `["…"]`: a bracketed JSON string literal (escapes as in
  JSON, with U+0085, U+2028 and U+2029 also escaped). `json.loads` of the
  bracket contents returns the original key;
- an array element is `[i]`, zero-based;
- a scalar or empty container at the document root has the path `$`. A key
  named `$` is not plain, so it renders as `["$"]`.

Each path parses back to exactly one key sequence, so `a.b` (key `b` inside
`a`), `["a.b"]` (one key containing a dot), `c[0]` (array index) and
`["c[0]"]` (one key) never collide.

Values:

- numbers keep their exact source literal: `243.40`, `1e-7`, `-0` and
  integers of any length are not reformatted;
- `true`, `false` and `null` are written as such; empty containers are `{}`
  and `[]`;
- strings are decoded (`\u00e9` becomes `é`, `\"` becomes `"`) and written
  without quotes. Each line break inside a string — `\r\n` as one break, and
  every other boundary recognised by Python `str.splitlines()` (`\n`, `\r`,
  U+000B, U+000C, U+001C–U+001E, U+0085, U+2028, U+2029) — becomes one space.
  No other whitespace is changed, so each leaf stays on exactly one line.

The value side is evidence text, not a serialization: a string `"true"` and the
literal `true` render identically. Path and line structure are unambiguous;
value types are not preserved.

Parsing is strict and fails closed. Each failure carries one fixed detail that
never echoes source text:

| Failure | Detail | Cause |
|---|---|---|
| `source_media_unsupported` | `application/json: invalid json` | syntax error, trailing data, byte-order mark, `NaN`/`Infinity`, raw control character in a string, a lone UTF-16 surrogate escape, or a number containing a non-ASCII digit |
| `source_media_unsupported` | `application/json: duplicate object key` | any object repeats a key |
| `source_media_unsupported` | `application/json: nesting exceeds limit` | containers nested deeper than 64 |
| `source_too_large` | `application/json: value count exceeds limit` | the pre-parse bound exceeds 1,000,000 values |

The value bound is checked before parsing, because a parsed Python object tree
can need tens of times the memory of the body. It counts every `,`, `[` and
`{` in the body plus one, including any inside strings, so it can only
overestimate. Text-heavy bodies with many commas inside strings may therefore
be refused, but cannot exceed the bound.

Nesting is also checked before parsing. The standard-library parser recurses
once per container, so a body of a few thousand brackets can exhaust a small
thread stack before any post-parse check runs. A linear, string-aware scan
counts brackets outside strings and stops at depth 65. Checks run in this
order: value bound, nesting, then strict parsing. A body that is both malformed
and too deep therefore reports `nesting exceeds limit`.

The whole document is validated before rendering, so validity never depends on
the character limit. Rendering stops once the configured
`max_extracted_characters` is exceeded and the window is `truncated`, exactly
as for other text; a lossy charset decode is `unknown`. The renderer keeps the
open path as a list of steps and builds each line, key and value only as far
as the remaining character budget, so its memory beyond parsing is bounded by
that budget rather than by nesting depth times key length.

A JSON body has no markup, so the HTML byte-to-text ratio cannot reveal a
shell. The v1 window classification instead treats a tiny rendered window as
the JSON analogue of a shell — an error or empty-result envelope served behind
a 2xx status:

- `empty`: the root is `{}`, `[]`, `null` or a blank string;
- `hollow`: at most 4,096 rendered characters that match a block-page pattern
  (for example `{"error":"Too many requests"}`), the same length bound HTML
  uses;
- `sparse`: any other window under 256 rendered characters (for example
  `{"message":"not found"}`);
- otherwise `complete`.

These bounds belong to `json-leaf-text/v1` and are re-applied on replay; a
different bound requires a new extractor version. For the same reason v1
holds its own frozen copy of the block-page patterns, identical to the HTML
patterns when v1 was defined. A later edit to the HTML patterns does not
change how stored v1 JSON windows classify. A small but genuine record is
also classified `sparse`. An excerpt found in it still anchors, but absence
cannot be concluded and canonical snapshot resolution reports it as an
incomplete evidence window. These JSON rules apply only to `json-leaf-text/v1`
windows; HTML and plain-text classification is unchanged.

### Change from raw JSON capture

JSON capture itself did change. Up to 0.2.0a3, the HTTP resolver stored an
`application/json` body as raw decoded text under `http-text/v2`. Built-in
captures now render it as `json-leaf-text/v1`:

- a new capture of the same bytes has different text, window and snapshot
  hashes;
- bodies that raw capture accepted now fail closed: duplicate object keys, a
  UTF-8 byte-order mark, `NaN` or `Infinity`, lone surrogate escapes, numbers
  with non-ASCII digits, or nesting deeper than 64
  (`source_media_unsupported`), and bodies over the value bound
  (`source_too_large`);
- small JSON envelopes that raw capture recorded as `complete` are now
  `sparse`, `hollow` or `empty`.

Stored raw-JSON snapshots replay unchanged under `http-text/v2`; replay never
re-extracts them. Live-to-replay equivalence between a new JSON capture and an
old raw-JSON snapshot therefore reports `different`. A JSON body served as
`text/plain` is still stored as raw `http-text/v2`. See
[MIGRATION](./MIGRATION.md).

## Replay compatibility

V2 and v3 snapshots preserve the exact window object. Evidence-window v1
objects remain valid and replay unchanged. Loading a successful source snapshot v1
snapshot constructs a hash-bound window over its stored text with
`truncation: unknown` and `extraction_method: legacy-snapshot/v1`. This retains
replay access without inventing a historical completeness claim. Consequently,
a missing excerpt in a v1 snapshot becomes `evidence_window_incomplete`, while
an excerpt found inside that snapshot remains `excerpt_found`.

Replay never re-extracts the source, so a recorded producer identity that differs
from the currently installed library or runtime is reported as
`extractor_identity_mismatch` detail without invalidating the stored evidence.
Any workflow claiming fresh-extraction equivalence across producer identities
must gate that comparison separately; ordinary replay makes no such claim.

Failure snapshots remain `groundnut-source-failure-snapshot/v1`; they contain
no searchable evidence window.

## Mechanical anchor methods

`byte_exact` proves that the supplied excerpt is a verbatim substring of the
stored evidence window. `normalised` proves presence only after named mechanical
changes (`case`, `whitespace`, `quotes`, `dashes`, and/or `punctuation`). `fuzzy`
is a diagnostic similarity method and can produce only `ambiguous` or
`not_found`, never `found`. None of these methods proves semantic support or
truth. Semantic-support admission remains the separate project tracked in
issue #18.

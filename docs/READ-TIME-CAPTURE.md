# Declared read-time capture

**Declaration:** `groundnut-capture-declaration/v2` or
`groundnut-capture-declaration/v3`
**Receipt:** `groundnut-read-capture/v1`
**Batch request:** `groundnut-read-capture-request/v2`

`groundnut-capture` is a narrow producer boundary for a host that reads a cited
source. It archives the first successful or failed read into Groundnut's source
snapshot contract. Canonical URI is the replay join; a later capture of that
URI replays the frozen observation even when another phase supplies a different
host label. It does not fetch and overwrite the first read.

The host must declare, before dispatch:

- a stable connector name;
- capture intent (`evidence_verification`);
- the allowed media types.

The declaration is canonicalized and hash-bound into every capture receipt.
HTML, XHTML, plain text and text-layer PDFs are the admitted media classes.
Other media produce the explicit `source_media_unsupported` failure. Paywalls,
unreachable sources and PDFs without a usable text layer retain their existing
failure states.

## Live acquisition security status

Groundnut's shared resolver permits only absolute HTTP(S) URIs without embedded
credentials. It rejects DNS answers that include non-public IPv4 or IPv6
destinations, applies the same policy to redirects, bounds encoded and decoded
response bytes, and limits admitted media, PDF pages and extracted characters.
The default transport connects to the validated address while retaining the
original hostname for the Host header and TLS verification. PDF extraction runs
in a separate worker with wall-clock, CPU, resident-memory and output ceilings.
Policy rejection and size rejection remain distinct acquisition failures.
The parent passes PDF bytes through a private temporary file, avoiding partial
pipe writes under load. A prior `pdf_worker_timeout` failure remains replayable
in `replay_only` mode but is retried by a later `snapshot_preferred` capture.

Text responses honor a declared HTTP charset, then an HTML meta charset, and
finally UTF-8. The chosen charset is recorded in the extraction method. Any
replacement-character decode is marked `unknown` rather than `complete` so a
mis-decoded window cannot establish definite quote absence.

These controls are **security work in progress**, not a comprehensive security
review. They have not yet passed independent adversarial review. Custom injected
HTTP or DNS transports require an explicit privileged opt-in and do not inherit
the default connection-pinning guarantee. PDF resource enforcement combines
native process limits with a parent-side resident-memory watchdog because OS
facilities differ. The current boundary, tests and required future admission are
recorded in the
[security hardening plan](./plans/security-hardening-plan-v1.md).

## Secret boundary

Canonical capture artifacts contain the public source identity, normalized
text, status, media type, retrieval time, evidence window and hashes. They have
no field for request headers, response headers, cookies, authorization values
or connector session state. Query parameters are default-deny: the connector
may use the original URI to fetch, but canonical identity retains only parameter
names declared by policy. V2 retains its global `retained_query_parameters`
contract for byte-identical replay. V3 uses exact lower-case host entries in
`retained_query_parameters_by_host`; an undeclared host retains no query key.
Wildcards are not accepted. Credential-shaped parameter names cannot be
declared retainable. User
information is rejected. Public path segments are retained verbatim: path-word
blocklists produce false positives and silently change the cited resource.

A hash-bound snapshot identity claim makes a producer fail closed when two
distinct public raw URIs—even across capture sessions—collapse to the same
canonical snapshot. Credential-shaped query values are excluded from that
comparison so token rotation does not create a false collision. Record-bearing
query parameters must be declared retainable.

Every v3 receipt records the query keys present, retained and non-sensitively
dropped, plus a count of credential-shaped dropped keys. Values are never
copied into that policy record and credential-shaped names are redacted. A
retained value can appear only in the canonical URI, where policy explicitly
permits it. This exposes a stripped record identifier without claiming that an
HTTP 200 response is the requested record.

## Canonical replay resolution

`resolve_snapshot(reference, declaration, store)` is the public citation join.
It canonicalizes the raw citation once, computes the one snapshot key, and
loads only that path. It never fetches, scans another directory or retries a
second URI. Its result keeps both raw and canonical identities and reports one
of `snapshot_missing`, `source_changed`, `http_status`, `empty_text`,
`incomplete_evidence_window`, or `hollow_capture` when no usable observation is
available.

`source_id` remains recorded attribution, but it is not snapshot identity. This
is also the migration rule for snapshots produced before the URI join was made
explicit: Groundnut accepts the stored observation by URI and presents it under
the source id requested by the current canonical run. No snapshot bytes are
rewritten.

The integration fixture deliberately gives its connector high-entropy
authorization, cookie and private-response-header sentinels. It scans snapshots,
receipts, logs, standard streams and forced-failure output for raw, case-folded,
URL-encoded, base64, hexadecimal, JSON-escaped, digest and delimiter-split forms.
Connector exception text and unbounded failure detail are replaced with bounded
diagnostics before archiving. A domain-separated, truncated SHA-256 reference
lets operators recognize two identical redacted failures or distinguish a new
one without publishing the raw detail. This proves the producer boundary does not
serialize those values. It does not claim that arbitrary source body text can
be classified as secret.

## Command boundary

```json
{
  "schema": "groundnut-read-capture-request/v2",
  "snapshot_directory": "snapshots",
  "declaration": {
    "connector": "public_web",
    "intent": "evidence_verification",
    "media_types": ["text/html", "application/pdf"],
    "retained_query_parameters_by_host": {
      "api.nsf.gov": ["AWD_ID"],
      "corp.sec.state.ma.us": ["FEIN"],
      "journals.plos.org": ["id"]
    }
  },
  "sources": [
    {"source_id": "source-1", "uri": "https://example.test/evidence"}
  ]
}
```

Run live capture only when the host's approved configuration authorizes it:

```bash
groundnut-capture capture-request.json --out capture-receipt.json --allow-live
```

Omitting `--allow-live` fails closed. Replay uses the same stored snapshot and
`SnapshotFirstResolver` contract as canonical checks and equivalence testing.

The shipped HTML and PDF fixtures are sanitized conformance examples. A real
second-deck live/replay/replay receipt remains an operational validation, not a
claim made by these fixtures.

# Declared read-time capture

**Declaration:** `groundnut-capture-declaration/v2`
**Receipt:** `groundnut-read-capture/v1`
**Batch request:** `groundnut-read-capture-request/v2`

`groundnut-capture` is a narrow producer boundary for a host that reads a cited
source. It archives the first successful or failed read into Groundnut's source
snapshot contract. A later capture under the same source identity replays the
frozen observation; it does not fetch and overwrite it.

The host must declare, before dispatch:

- a stable connector name;
- capture intent (`evidence_verification`);
- the allowed media types.

The declaration is canonicalized and hash-bound into every capture receipt.
HTML, XHTML, plain text and text-layer PDFs are the admitted media classes.
Other media produce the explicit `source_media_unsupported` failure. Paywalls,
unreachable sources and PDFs without a usable text layer retain their existing
failure states.

## Secret boundary

Canonical capture artifacts contain the public source identity, normalized
text, status, media type, retrieval time, evidence window and hashes. They have
no field for request headers, response headers, cookies, authorization values
or connector session state. Query parameters are default-deny: the connector
may use the original URI to fetch, but canonical identity retains only parameter
names declared in `retained_query_parameters`. The default is an empty query.
Credential-shaped parameter names cannot be declared retainable. User
information and credential-shaped path segments are rejected.

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
    "retained_query_parameters": []
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

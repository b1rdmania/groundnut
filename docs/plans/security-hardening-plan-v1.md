# Groundnut acquisition and locator hardening plan v1

**Status:** work in progress
**Security posture:** Groundnut has not completed a comprehensive security review.
**Trigger:** findings independently reproduced after the 27 August 2026 review of
`research-pipelin3/claude-research-pipeline` PR #48.
**Order:** secure acquisition boundary -> preserve unresolvable evidence -> adversarial
tests -> release review -> resume semantic-support admission.

## Purpose

Groundnut fetches evidence selected by a research workflow. That URI and the bytes at
the other end are untrusted. At the start of this batch, `HttpResolver` accepted every
scheme understood by `urllib`, followed redirects without applying a Groundnut policy,
and read a response without a byte limit. A `data:` URI was reproduced as a successful
source. The artifact extractor also kept the sentence carrying a bare locator while
discarding the locator itself when no URL was present.

This batch closes those known boundaries without claiming that it completes a security
review. Provenance, replay and fail-closed evidence semantics are existing strengths;
they do not make live acquisition safe by themselves.

## Scope

### A. Shared HTTP resolver boundary

The policy belongs in `groundnut.sources.HttpResolver`, which is used by canonical runs
and declared read-time capture. Wrappers may be stricter, but they must not be able to
weaken these core defaults accidentally.

The injectable opener and address resolver are privileged deterministic-test or
specialist-host seams, not untrusted configuration. Supplying either requires an
explicit `allow_injected_transport=True` opt-in. Groundnut still validates the initial
and reported final URI, but arbitrary injected code is outside the default transport's
pre-request redirect guarantee.

The resolver will:

1. accept only absolute ASCII `http` and `https` URIs with a hostname (IRI
   characters must be encoded before this boundary);
2. reject embedded credentials;
3. resolve every hostname and reject the destination when any returned IPv4 or IPv6
   address is not globally routable, including loopback, private, link-local,
   unspecified, multicast, reserved and cloud-metadata destinations;
4. apply the same URI and address checks before every automatic redirect;
5. verify the final response URI again before accepting bytes;
6. reject a declared `Content-Length` above the configured response limit and otherwise
   read at most `limit + 1` bytes;
7. decode only identity, gzip and deflate transfer content, with separate compressed and
   decompressed byte ceilings;
8. admit only textual HTTP media types, JSON/XML, XHTML and PDF;
9. bound extracted text, PDF page count and input PDF bytes; and
10. return typed, fail-closed acquisition outcomes instead of converting a policy block
    or oversized body into an empty source.

Default limits are part of the executable contract and will be constructor parameters so
tests and specialist hosts can choose a lower ceiling without disabling the boundary.

### Connection-bound DNS enforcement

The default transport validates the initial URI and every redirect, then opens the
socket directly to one of the addresses returned by that validation. It verifies the
connected peer and retains the original hostname for the HTTP Host header, TLS SNI and
certificate verification. It therefore does not perform a second hostname lookup
between policy admission and connection establishment.

Arbitrary injected HTTP or DNS transports cannot inherit that guarantee. They remain a
privileged, explicit opt-in for deterministic tests or specialist hosts. The default
transport also deliberately does not inherit ambient proxy configuration; proxy support
would need its own destination and connection policy before admission.

This implementation remains **security work in progress** until independently reviewed,
even when all tests below pass.

### PDF and decompression boundary

HTTP content decoding is bounded before materialisation. PDF parsing runs in a separate
Python worker bounded by input bytes, pages, extracted characters, serialized output,
wall-clock time and CPU time. Native address-space limiting is used where supported; the
parent independently observes resident memory and kills a worker that crosses the
configured ceiling. If resident memory cannot be observed, extraction fails closed.

This contains parser failure and resource use outside the long-lived resolver process;
it is not a claim that `pypdf` is safe or that the limits have passed hostile-PDF review.
Operating-system differences and the watchdog sampling interval remain review surface.

### B. Bare locator preservation

A locator is evidence metadata even when it has no public URL. Markdown and rendered HTML
extractors will retain an adjacent locator-only marker on the sentence it describes.

The canonical result will distinguish:

- `unresolvable_source`: a locator was declared but no fetchable source URI exists;
- `source_unavailable`: a URI exists but acquisition failed;
- `not_applicable`: no external evidence apparatus was declared; and
- `no_excerpt`: a readable URI exists but only a locator, not a verbatim excerpt, was
  supplied.

Semantic support for a bare locator will be `source_unavailable` with failure
`unresolvable_source`; no detector may run. The locator remains present in the claim and
assessment payloads.

Coverage will count both URL citations and bare locators as declared evidence. It will
report resolvability separately so adding a locator cannot make source accessibility look
better. The verification metrics schema will advance rather than silently changing the
meaning of an existing schema version.

The IC ledger will place bare locators in `citation_unconfirmed`, detail
`unresolvable_source`, rather than `own_reasoning`.

## Out of scope

- HTML report sanitisation and database RLS findings in PR #48 belong to their owning
  repositories.
- The retired `ic-verify-groundnut-intake` Sentinel lane is not Groundnut core. If revived,
  it should become optional after Groundnut output is written.
- Semantic-support detector admission remains issue #18 and resumes after this batch.
- This work does not assert source truth, semantic support or evidence authority.
- This work is not a penetration test or a comprehensive security review.

## Acceptance tests

### URI and network policy

- `data:`, `file:`, scheme-relative, credential-bearing and hostless URIs fail closed.
- Literal loopback, RFC1918/private, link-local, unspecified, multicast and reserved IPv4
  and IPv6 addresses fail closed.
- A hostname is rejected when DNS returns any non-global address.
- A redirect to a disallowed scheme or destination is rejected before the redirected
  request is issued by Groundnut's default opener.
- A permitted public HTTPS URI and a permitted public redirect remain usable under an
  injected deterministic resolver.
- The default socket connection uses the address admitted during preflight rather than
  resolving the hostname a second time, while HTTPS retains hostname verification.

### Resource limits

- Oversized declared `Content-Length` is rejected without a body read.
- An undeclared oversized response is rejected after at most `limit + 1` bytes.
- Gzip and deflate payloads cannot exceed the decompressed ceiling.
- Unsupported content encodings and media types fail closed.
- PDF page and extracted-character truncation is explicit in the evidence window.
- PDF parsing does not execute in the resolver process; wall-clock, CPU, resident-memory
  and output failures produce typed fail-closed outcomes.

### Locator contract

- Markdown and HTML bare locator markers survive extraction with their exact value.
- The associated claim remains in the same claim population and location.
- Mechanical verification emits `unresolvable_source`.
- Semantic support emits `source_unavailable/unresolvable_source` without invoking a
  detector.
- Metrics count the declared locator while keeping resolvability and accessibility
  separate.
- The ledger records `citation_unconfirmed:unresolvable_source`.
- Existing URL + locator behaviour and snapshot replay remain unchanged.

## Release and review gate

Before merge:

1. focused acquisition, artifact, verification, support and ledger tests pass;
2. the full suite passes once at the release boundary;
3. the diff is reviewed for fail-open exception paths and schema drift;
4. documentation says `security work in progress` and lists the remaining transport,
   PDF and independent-review boundaries;
5. no release note says the resolver or Groundnut is secure, hardened completely,
   audited or approved; and
6. the change receives a separate security-focused review before any stronger posture is
   claimed.

## Implementation sequence

1. Add typed source-policy and source-size failures.
2. Add URI/address validation and a policy-aware default redirect handler.
3. Add bounded response/content decoding and extracted-text ceilings.
4. Extend Markdown and HTML extraction for bare locators.
5. Add the unresolvable mechanical/support outcomes and metrics schema migration.
6. Route bare locators into the citation-unconfirmed ledger bucket.
7. Add adversarial fixtures and update operational documentation.
8. Run focused tests, then one full suite and a final security-boundary review.
9. Bind the default socket connection to its admitted address while preserving TLS
   hostname verification.
10. Move PDF parsing to a resource-limited worker with parent-side memory observation.

## Implementation record — 28 August 2026

Rebased onto `main@0e61510` and implemented on
`codex/security-hardening-batch` for the `0.2.0a1` boundary:

- shared URI, public-address and redirect policy;
- connection-bound address enforcement with TLS hostname verification preserved;
- encoded, decoded, media, PDF-page and extracted-character ceilings;
- isolated PDF parsing with wall-clock, CPU, resident-memory and output ceilings;
- typed `source_policy_blocked` and `source_too_large` acquisition failures;
- Markdown, HTML and structured bare-locator preservation;
- mechanical `unresolvable_source`, fail-closed semantic support, claim
  verification v4 and metrics v5;
- ledger segmenter v7 routing bare locators to
  `citation_unconfirmed:unresolvable_source`, on top of the document-coordinate
  handling already merged in PR #39; and
- explicit security-work-in-progress language in the README, security policy
  and capture documentation.

Verification evidence:

- focused acquisition/capture/snapshot-resolution/artifact/verification/support/
  ledger suite: 176 passed;
- full repository suite: 392 passed;
- direct default-resolver probes block `data:`, loopback and
  `169.254.169.254`; and
- `git diff --check` and Python bytecode compilation pass.

This implementation record does not change the security posture at the top of
the plan. The connection-bound DNS and PDF isolation controls are implemented,
but a separate security-focused review remains open before any stronger claim is
allowed.

The pre-PR security review added fail-closed handling and regression cases for
raw control and non-ASCII URI characters, backslash ambiguity, legacy loopback
spellings, IPv4-mapped IPv6, malformed content lengths, and invalid or
concatenated compressed streams. This was an implementation review, not the
separate independent security review required for a stronger posture claim.

## Alpha merge waiver — 28 August 2026

The repository owner explicitly waived release-gate item 6 for merging the
`0.2.0a1` alpha into `main`. The independent security review remains incomplete.
This waiver does not change Groundnut's security-work-in-progress posture and
does not authorize a stable `0.2.0` release, a security approval claim, or the
removal of the review requirement.

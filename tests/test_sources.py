import json
import io
import urllib.error
from pathlib import Path
import zlib

import pytest
import groundnut.sources as source_module

from groundnut.sources import (
    EvidenceWindow,
    FileResolver,
    HttpResolver,
    _PinnedHTTPTransport,
    _validate_public_http_uri,
    ResolvedSource,
    SnapshotStore,
    SourceReference,
    SourceResolution,
    html_to_text,
)
from groundnut.provenance import sha256_text
from groundnut.verification import Claim, verify_claim


HOLLOW_CAPTURE_FIXTURES = (
    Path(__file__).parent / "fixtures" / "hollow_capture_cases.json"
)


def _public_addresses(hostname, port):
    return ("93.184.216.34",)


def _http_resolver(**kwargs):
    return HttpResolver(
        address_resolver=_public_addresses,
        allow_injected_transport=True,
        **kwargs,
    )


def test_file_resolver_returns_hashed_source(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Evidence text")
    result = FileResolver().resolve(SourceReference("s1", str(path)))

    assert result.ok is True
    assert result.source.text == "Evidence text"
    assert result.source.record.characters == 13
    assert result.source.evidence_window.truncation == "complete"
    assert result.source.evidence_window.original_bytes == 13


def test_file_resolver_snapshot_round_trip_keeps_local_identity_key(tmp_path):
    path = tmp_path / "local source.txt"
    path.write_text("Local evidence text")
    reference = SourceReference("local", str(path))
    resolved = FileResolver().resolve(reference)
    store = SnapshotStore(tmp_path / "snapshots")

    snapshot = store.archive(resolved.source)
    replay = store.load(reference)

    assert snapshot == store.path_for(reference.uri)
    assert replay.ok
    assert replay.source.text == "Local evidence text"
    assert replay.source.final_uri == reference.uri


def test_missing_file_is_honest_failure(tmp_path):
    result = FileResolver().resolve(
        SourceReference("missing", str(tmp_path / "absent.txt"))
    )

    assert result.ok is False
    assert result.failure == "source_unreachable"


def test_snapshot_round_trip_and_tamper_detection(tmp_path):
    reference = SourceReference("s1", "https://example.test/source")
    source = ResolvedSource(
        reference=reference,
        text="Frozen source text",
        fetched_at="2026-08-17T12:00:00+00:00",
        status=200,
        media_type="text/plain",
    )
    store = SnapshotStore(tmp_path / "snapshots")
    path = store.archive(source)

    loaded = store.load(reference)
    assert loaded.ok is True
    assert loaded.source.text == source.text
    assert loaded.source.final_uri == reference.uri
    assert loaded.source.evidence_window == source.evidence_window

    payload = json.loads(path.read_text())
    assert payload["schema"] == "groundnut-source-snapshot/v3"
    assert payload["final_uri"] == reference.uri
    assert len(payload["snapshot_sha256"]) == 64
    assert payload["evidence_window"]["captured_characters"] == len(source.text)
    payload["text"] = "rewritten"
    path.write_text(json.dumps(payload))
    tampered = store.load(reference)
    assert tampered.ok is False
    assert tampered.failure == "source_changed"


def test_failure_snapshot_round_trip_preserves_observation(tmp_path):
    reference = SourceReference("s1", "https://example.test/paywall")
    resolution = SourceResolution(
        source=None, failure="source_paywalled", detail="http_403"
    )
    store = SnapshotStore(tmp_path / "snapshots")
    path = store.archive_failure(reference, resolution)

    payload = json.loads(path.read_text())
    assert payload["schema"] == "groundnut-source-failure-snapshot/v1"
    assert "final_uri" not in payload
    assert "snapshot_sha256" not in payload
    assert store.load(reference) == resolution


def test_html_to_text_ignores_script_and_decodes_entities():
    assert html_to_text(
        "<main>Revenue &amp; margin</main><script>secret()</script>"
    ) == "Revenue & margin"


class _Headers:
    def __init__(self, media_type, values=None):
        self.media_type = media_type
        self.values = values or {}

    def get_content_type(self):
        return self.media_type

    def get(self, name, default=None):
        return self.values.get(name, default)


class _Response:
    status = 200

    def __init__(self, body, media_type="text/html", headers=None, final_uri=None):
        self.body = body
        self.headers = _Headers(media_type, headers)
        self.final_uri = final_uri

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def geturl(self):
        return self.final_uri or "https://example.test/final"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_http_resolver_normalizes_html_without_live_network():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(b"<p>Source <b>fact</b></p>")
    )
    result = resolver.resolve(SourceReference("web-1", "https://example.test"))

    assert result.ok is True
    assert result.source.text == "Source fact"
    assert result.source.status == 200
    assert result.source.final_uri == "https://example.test/final"
    assert result.source.evidence_window.truncation == "complete"
    assert result.source.evidence_window.original_bytes == len(
        b"<p>Source <b>fact</b></p>"
    )
    assert result.source.evidence_window.captured_characters == len("Source fact")


def test_http_resolver_records_no_redirect_final_uri():
    requested = "https://example.test/article"
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"Evidence", media_type="text/plain", final_uri=requested
        )
    )

    result = resolver.resolve(SourceReference("no-redirect", requested))

    assert result.ok
    assert result.source.final_uri == requested


def test_http_resolver_records_allowed_same_host_redirect_path():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"Evidence",
            media_type="text/plain",
            final_uri="https://example.test/articles/final",
        )
    )

    result = resolver.resolve(
        SourceReference("same-host", "https://example.test/articles/start")
    )

    assert result.ok
    assert result.source.final_uri == "https://example.test/articles/final"


def test_http_resolver_records_allowed_cross_host_redirect_destination():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"Evidence",
            media_type="text/plain",
            final_uri="https://records.example.test/public/page",
        )
    )

    result = resolver.resolve(
        SourceReference("cross-host", "https://example.test/start")
    )

    assert result.ok
    assert result.source.final_uri == "https://records.example.test/public/page"


def test_http_resolver_drops_secret_shaped_redirect_query_and_fragment(tmp_path):
    secret = "do-not-persist"
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"Evidence",
            media_type="text/plain",
            final_uri=(
                "https://records.example.test/public/page"
                f"?access_token={secret}&signature=also-secret#private"
            ),
        )
    )

    result = resolver.resolve(
        SourceReference("secret-query", "https://example.test/start")
    )

    assert result.ok
    assert result.source.final_uri == "https://records.example.test/public/page"
    assert secret not in result.source.final_uri
    snapshot = SnapshotStore(tmp_path).archive(result.source)
    assert secret not in snapshot.read_text()


def test_http_resolver_requires_explicit_opt_in_for_injected_transport():
    with pytest.raises(ValueError, match="privileged"):
        HttpResolver(opener=lambda request, timeout: _Response(b"source"))
    with pytest.raises(ValueError, match="privileged"):
        HttpResolver(address_resolver=_public_addresses)


@pytest.mark.parametrize(
    "uri",
    [
        "data:text/plain,self-authored",
        "file:///tmp/source.txt",
        "//example.test/source",
        "https://user:password@example.test/source",
        "https:///missing-host",
        "https://example.test/line\nbreak",
        "https://example.test/space in path",
        "https://example.test/unicode-\u2028-path",
        "https://example.test/backslash\\path",
        "https://%00example.test/source",
    ],
)
def test_http_resolver_rejects_non_http_and_ambiguous_source_uris(uri):
    calls = []
    resolver = HttpResolver(
        opener=lambda request, timeout: calls.append(request),
        address_resolver=_public_addresses,
        allow_injected_transport=True,
    )

    result = resolver.resolve(SourceReference("blocked", uri))

    assert result.failure == "source_policy_blocked"
    assert calls == []


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::",
        "ff02::1",
    ],
)
def test_http_resolver_rejects_non_public_ipv4_and_ipv6(address):
    calls = []
    resolver = HttpResolver(
        opener=lambda request, timeout: calls.append(request),
        address_resolver=lambda hostname, port: (address,),
        allow_injected_transport=True,
    )

    result = resolver.resolve(SourceReference("blocked", "https://host.test/source"))

    assert result.failure == "source_policy_blocked"
    assert result.detail.startswith("non_public_address:")
    assert calls == []


def test_http_resolver_rejects_hostname_when_any_dns_answer_is_non_public():
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(b"should not be read"),
        address_resolver=lambda hostname, port: (
            "93.184.216.34",
            "169.254.169.254",
        ),
        allow_injected_transport=True,
    )

    result = resolver.resolve(SourceReference("mixed", "https://host.test/source"))

    assert result.failure == "source_policy_blocked"
    assert result.detail == "non_public_address:169.254.169.254"


def test_default_transport_validates_redirect_before_second_request():
    class RedirectResponse:
        status = 302
        headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

        def close(self):
            pass

    opened = []

    class ProbeTransport(_PinnedHTTPTransport):
        def _open(self, target, headers, timeout):
            opened.append(target.uri)
            return RedirectResponse()

    def addresses(hostname, port):
        return (
            "169.254.169.254"
            if hostname == "169.254.169.254"
            else "93.184.216.34",
        )

    transport = ProbeTransport(
        lambda uri: _validate_public_http_uri(uri, addresses)
    )

    with pytest.raises(ValueError, match="non_public_address"):
        transport(
            source_module.urllib.request.Request("https://example.test/start"),
            timeout=1,
        )

    assert opened == ["https://example.test/start"]


def test_default_transport_connects_to_the_preflighted_address(monkeypatch):
    calls = []

    def connect(address, timeout, source_address, *, all_errors):
        calls.append((address, timeout, source_address, all_errors))
        return object()

    monkeypatch.setattr(source_module.socket, "create_connection", connect)
    target = _validate_public_http_uri(
        "http://example.test:8080/source", _public_addresses
    )
    connection = _PinnedHTTPTransport(
        lambda uri: target
    )._connection(target, "93.184.216.34", 7)

    result = connection._create_connection(("example.test", 8080), 7)

    assert result is not None
    assert calls == [(('93.184.216.34', 8080), 7, None, False)]


def test_http_resolver_revalidates_final_response_uri():
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(
            b"secret",
            media_type="text/plain",
            final_uri="http://127.0.0.1/private",
        ),
        address_resolver=lambda hostname, port: (
            "127.0.0.1" if hostname == "127.0.0.1" else "93.184.216.34",
        ),
        allow_injected_transport=True,
    )

    result = resolver.resolve(SourceReference("redirect", "https://example.test/start"))

    assert result.failure == "source_policy_blocked"


def test_http_resolver_rejects_declared_oversize_without_reading_body():
    response = _Response(
        b"unused",
        media_type="text/plain",
        headers={"Content-Length": "101"},
    )
    reads = []
    response.read = lambda size=-1: reads.append(size) or b"unused"
    resolver = _http_resolver(
        opener=lambda request, timeout: response,
        max_response_bytes=100,
    )

    result = resolver.resolve(SourceReference("large", "https://example.test/large"))

    assert result.failure == "source_too_large"
    assert reads == []


def test_http_resolver_bounds_undeclared_response_body():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(b"x" * 101, media_type="text/plain"),
        max_response_bytes=100,
    )

    result = resolver.resolve(SourceReference("large", "https://example.test/large"))

    assert result.failure == "source_too_large"
    assert result.detail == "response_body_exceeds_limit"


@pytest.mark.parametrize("declared", ["-1", "not-a-number", "10, 10"])
def test_http_resolver_rejects_invalid_content_length(declared):
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"body",
            media_type="text/plain",
            headers={"Content-Length": declared},
        )
    )

    result = resolver.resolve(SourceReference("length", "https://example.test/length"))

    assert result.failure == "source_policy_blocked"
    assert result.detail == "invalid_content_length"


def _gzip(data):
    compressor = zlib.compressobj(wbits=16 + zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def test_http_resolver_bounds_decompressed_response_body():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            _gzip(b"x" * 101),
            media_type="text/plain",
            headers={"Content-Encoding": "gzip"},
        ),
        max_response_bytes=100,
        max_decompressed_bytes=100,
    )

    result = resolver.resolve(SourceReference("zip", "https://example.test/zip"))

    assert result.failure == "source_too_large"
    assert result.detail == "decompressed_body_exceeds_limit"


def test_http_resolver_decodes_bounded_gzip_content():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            _gzip(b"bounded source"),
            media_type="text/plain",
            headers={"Content-Encoding": "gzip"},
        )
    )

    result = resolver.resolve(SourceReference("zip", "https://example.test/zip"))

    assert result.ok is True
    assert result.source.text == "bounded source"


@pytest.mark.parametrize("body", [b"not gzip", _gzip(b"first") + _gzip(b"second")])
def test_http_resolver_rejects_invalid_or_concatenated_gzip(body):
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            body,
            media_type="text/plain",
            headers={"Content-Encoding": "gzip"},
        )
    )

    result = resolver.resolve(SourceReference("gzip", "https://example.test/gzip"))

    assert result.failure == "source_policy_blocked"
    assert result.detail == "invalid_compressed_body"


def test_http_resolver_decodes_bounded_raw_deflate_content():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    body = compressor.compress(b"raw deflate source") + compressor.flush()
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            body,
            media_type="text/plain",
            headers={"Content-Encoding": "deflate"},
        )
    )

    result = resolver.resolve(SourceReference("deflate", "https://example.test/deflate"))

    assert result.ok is True
    assert result.source.text == "raw deflate source"


def test_http_resolver_rejects_unsupported_media_and_content_encoding():
    binary = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"binary", media_type="application/octet-stream"
        )
    ).resolve(SourceReference("binary", "https://example.test/binary"))
    encoded = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"encoded",
            media_type="text/plain",
            headers={"Content-Encoding": "br"},
        )
    ).resolve(SourceReference("br", "https://example.test/br"))

    assert binary.failure == "source_media_unsupported"
    assert encoded.failure == "source_policy_blocked"
    assert encoded.detail == "content_encoding_not_allowed"


def test_http_text_window_declares_extracted_character_truncation():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(
            b"abcdefghij", media_type="text/plain"
        ),
        max_extracted_characters=5,
    )

    result = resolver.resolve(SourceReference("text-window", "https://example.test/text"))

    assert result.ok is True
    assert result.source.text == "abcde"
    assert result.source.evidence_window.truncation == "truncated"
    assert result.source.evidence_window.original_characters == 10


def test_empty_html_window_is_incomplete_not_searched_and_absent():
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(b"<script>app()</script>")
    )
    reference = SourceReference("empty", "https://example.test/empty")
    result = resolver.resolve(reference)

    assert result.ok is True
    assert result.source.text == ""
    assert result.source.evidence_window.truncation == "empty"
    verification = verify_claim(
        Claim("missing", "Registry fact.", source=reference, excerpt="Registry fact."),
        result,
    )
    assert verification.outcome == "evidence_window_incomplete"


def test_sparse_html_shell_is_not_declared_complete():
    body = ("<script>" + "x" * 5000 + "</script><main>Enable JavaScript</main>").encode()
    resolver = _http_resolver(opener=lambda request, timeout: _Response(body))
    result = resolver.resolve(SourceReference("shell", "https://example.test/app"))

    assert result.ok is True
    assert result.source.text == "Enable JavaScript"
    assert result.source.evidence_window.truncation == "hollow"


def test_known_interstitial_shapes_are_hollow_and_unusable():
    fixtures = json.loads(HOLLOW_CAPTURE_FIXTURES.read_text())
    for index, fixture in enumerate(fixtures):
        body = fixture["html"].encode()
        reference = SourceReference(fixture["name"], f"https://example.test/{index}")
        result = _http_resolver(
            opener=lambda request, timeout, body=body: _Response(body)
        ).resolve(reference)
        assert result.source.evidence_window.truncation == fixture["expected"]
        if fixture["expected"] != "hollow":
            continue
        checked = verify_claim(
            Claim("challenge", "Claim", source=reference, excerpt=result.source.text),
            result,
        )
        assert checked.outcome == "evidence_window_incomplete"
        assert checked.anchor == "not_found"


def test_normal_short_record_and_long_article_with_block_word_remain_complete():
    short = b"<article>Grant AWD_ID 1234 was awarded on 2 May 2026.</article>"
    long = (
        "<article>" + "Primary record detail. " * 300 +
        "The article discusses Cloudflare and cookie policy in context.</article>"
    ).encode()
    for body in (short, long):
        result = _http_resolver(
            opener=lambda request, timeout, body=body: _Response(body)
        ).resolve(SourceReference("record", "https://example.test/record"))
        assert result.source.evidence_window.truncation == "complete"


def test_hollow_snapshot_round_trip_preserves_classification(tmp_path):
    reference = SourceReference("challenge", "https://example.test/challenge")
    result = _http_resolver(
        opener=lambda request, timeout: _Response(b"<main>Verify you are human to continue.</main>")
    ).resolve(reference)
    store = SnapshotStore(tmp_path)
    store.archive(result.source)
    replay = store.load(reference)
    assert replay.ok
    assert replay.source.evidence_window.truncation == "hollow"


def test_existing_complete_empty_snapshot_migrates_on_read(tmp_path):
    reference = SourceReference("host-label", "https://example.test/empty-legacy")
    legacy_window = EvidenceWindow(
        captured_bytes=0,
        captured_characters=0,
        truncation="complete",
        extraction_method="html.parser-visible-text/v1",
        text_sha256=sha256_text(""),
        original_bytes=1024,
        original_characters=1024,
    )
    store = SnapshotStore(tmp_path)
    store.directory.mkdir(parents=True, exist_ok=True)
    store.path_for(reference.uri).write_text(
        json.dumps(
            {
                "schema": "groundnut-source-snapshot/v2",
                "source_id": reference.source_id,
                "uri": reference.uri,
                "fetched_at": "2026-08-25T00:00:00Z",
                "status": 200,
                "media_type": "text/html",
                "sha256": sha256_text(""),
                "text": "",
                "evidence_window": legacy_window.to_dict(),
            },
            sort_keys=True,
        )
    )

    loaded = store.load(
        SourceReference("url:derived-by-report", reference.uri)
    )

    assert loaded.ok is True
    assert loaded.source.reference.source_id == "url:derived-by-report"
    assert loaded.source.final_uri == reference.uri
    assert loaded.source.evidence_window.truncation == "empty"


def test_http_resolver_keeps_paywall_distinct_from_unreachable():
    def paywall(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 403, "forbidden", {}, io.BytesIO()
        )

    result = _http_resolver(opener=paywall).resolve(
        SourceReference("web-2", "https://example.test/paywall")
    )

    assert result.ok is False
    assert result.failure == "source_paywalled"


def _pdf_bytes(*texts: str) -> bytes:
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        # pypdf cannot lay out text; build a minimal content stream by hand.
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 150 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_http_resolver_extracts_pdf_text_layer():
    body = _pdf_bytes("Revenue was 4.2 million.")
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(body, media_type="application/pdf")
    )
    result = resolver.resolve(SourceReference("pdf-1", "https://example.test/filing.pdf"))

    assert result.ok is True
    assert "Revenue was 4.2 million." in result.source.text
    assert result.source.media_type == "application/pdf"
    assert result.source.evidence_window.truncation == "complete"
    assert result.source.evidence_window.original_bytes == len(body)
    assert result.source.evidence_window.original_characters is None


def test_http_pdf_extraction_is_not_run_in_resolver_process(monkeypatch):
    body = _pdf_bytes("Isolated evidence.")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("in-process PDF extractor was called")

    monkeypatch.setattr(source_module, "_pdf_to_text_and_pages", fail_if_called)
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(body, media_type="application/pdf")
    )

    result = resolver.resolve(
        SourceReference("pdf-isolated", "https://example.test/isolated.pdf")
    )

    assert result.ok is True
    assert result.source.text == "Isolated evidence."


def test_isolated_pdf_worker_is_killed_at_memory_limit(monkeypatch):
    class MemoryHungryWorker:
        pid = 1234
        returncode = None
        killed = False

        def communicate(self, input=None, timeout=None):
            if self.killed:
                self.returncode = -9
                return (None, None)
            raise source_module.subprocess.TimeoutExpired("pdf-worker", timeout)

        def kill(self):
            self.killed = True

    worker = MemoryHungryWorker()
    monkeypatch.setattr(source_module.subprocess, "Popen", lambda *a, **k: worker)
    monkeypatch.setattr(source_module, "_resident_memory_bytes", lambda pid: 101)

    result = source_module._isolated_pdf_to_text_and_pages(
        b"%PDF",
        max_pages=1,
        max_characters=10,
        timeout_seconds=1,
        cpu_seconds=1,
        memory_bytes=100,
    )

    assert result == (None, None, False, "pdf_worker_memory_limit")
    assert worker.killed is True


def test_http_pdf_window_declares_page_limit_truncation():
    body = _pdf_bytes("Visible evidence.", "Hidden evidence after boundary.")
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(body, media_type="application/pdf"),
        max_pdf_pages=1,
    )
    result = resolver.resolve(SourceReference("pdf-window", "https://example.test/window.pdf"))

    assert result.ok is True
    assert "Visible evidence." in result.source.text
    assert "Hidden evidence" not in result.source.text
    assert result.source.evidence_window.truncation == "truncated"
    assert "max_pages=1" in result.source.evidence_window.extraction_method


def test_http_pdf_window_declares_extracted_character_truncation():
    body = _pdf_bytes("Visible evidence exceeds the small output boundary.")
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(body, media_type="application/pdf"),
        max_extracted_characters=16,
    )

    result = resolver.resolve(
        SourceReference("pdf-text-window", "https://example.test/window.pdf")
    )

    assert result.ok is True
    assert result.source.text == "Visible evidence"
    assert result.source.evidence_window.truncation == "truncated"
    assert "max_characters=16" in result.source.evidence_window.extraction_method


def test_http_resolver_reports_pdf_without_text_layer_as_unsupported():
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    resolver = _http_resolver(
        opener=lambda request, timeout: _Response(out.getvalue(), media_type="application/pdf")
    )
    result = resolver.resolve(SourceReference("pdf-2", "https://example.test/scan.pdf"))

    assert result.ok is False
    assert result.failure == "pdf_unsupported"


def test_v1_snapshot_replays_with_unknown_completeness(tmp_path):
    reference = SourceReference("legacy", "https://example.test/legacy")
    text = "Legacy captured text"
    store = SnapshotStore(tmp_path / "snapshots")
    store.directory.mkdir(parents=True, exist_ok=True)
    store.path_for(reference.uri).write_text(
        json.dumps(
            {
                "schema": "groundnut-source-snapshot/v1",
                "source_id": reference.source_id,
                "uri": reference.uri,
                "fetched_at": "2026-08-17T00:00:00Z",
                "status": 200,
                "media_type": "text/plain",
                "sha256": sha256_text(text),
                "text": text,
            },
            sort_keys=True,
        )
    )

    before = store.path_for(reference.uri).read_bytes()
    loaded = store.load(reference)
    assert loaded.ok is True
    assert loaded.source.final_uri == reference.uri
    assert store.path_for(reference.uri).read_bytes() == before
    assert loaded.source.evidence_window.truncation == "unknown"
    assert loaded.source.evidence_window.extraction_method == "legacy-snapshot/v1"
    assert loaded.source.evidence_window.text_sha256 == sha256_text(text)
    verification = verify_claim(
        Claim(
            "legacy-miss",
            "A later statement.",
            source=reference,
            excerpt="Text outside the legacy snapshot.",
        ),
        loaded,
    )
    assert verification.outcome == "evidence_window_incomplete"


def test_v3_snapshot_rejects_window_tampering(tmp_path):
    reference = SourceReference("s1", "https://example.test/window")
    source = ResolvedSource(reference, "Captured", "2026-08-17T00:00:00Z")
    store = SnapshotStore(tmp_path)
    path = store.archive(source)
    payload = json.loads(path.read_text())
    payload["evidence_window"]["captured_characters"] += 1
    path.write_text(json.dumps(payload))

    loaded = store.load(reference)
    assert loaded.failure == "source_changed"
    assert loaded.detail == "snapshot_evidence_window_invalid"


def test_v2_snapshot_replays_with_requested_uri_final_uri_without_rewrite(tmp_path):
    reference = SourceReference("legacy-v2", "https://example.test/v2")
    text = "V2 captured text"
    window = EvidenceWindow.from_text(
        text,
        truncation="complete",
        extraction_method="fixture/v1",
        original_bytes=len(text.encode()),
        original_characters=len(text),
    )
    store = SnapshotStore(tmp_path)
    store.directory.mkdir(parents=True, exist_ok=True)
    path = store.path_for(reference.uri)
    path.write_text(
        json.dumps(
            {
                "schema": "groundnut-source-snapshot/v2",
                "source_id": reference.source_id,
                "uri": reference.uri,
                "fetched_at": "2026-08-17T00:00:00Z",
                "status": 200,
                "media_type": "text/plain",
                "sha256": sha256_text(text),
                "text": text,
                "evidence_window": window.to_dict(),
            },
            sort_keys=True,
        )
    )
    before = path.read_bytes()

    loaded = store.load(reference)

    assert loaded.ok
    assert loaded.source.final_uri == reference.uri
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("final_uri", "detail"),
    [
        ("not a uri", "snapshot_final_uri_invalid:invalid_uri"),
        ("file:///tmp/source", "snapshot_final_uri_invalid:scheme_not_allowed"),
        ("https://-bad.example/path", "snapshot_final_uri_invalid:invalid_hostname"),
        ("https://localhost/path", "snapshot_final_uri_invalid:localhost_not_allowed"),
        (
            "https://foo.localhost/path",
            "snapshot_final_uri_invalid:localhost_not_allowed",
        ),
        (
            "http://127.0.0.1/private",
            "snapshot_final_uri_invalid:non_public_address:127.0.0.1",
        ),
        (
            "https://example.test/path?token=secret",
            "snapshot_final_uri_invalid:not_sanitized",
        ),
    ],
)
def test_v3_snapshot_invalid_final_uri_fails_closed(tmp_path, final_uri, detail):
    reference = SourceReference("v3-invalid", "https://example.test/requested")
    store = SnapshotStore(tmp_path)
    path = store.archive(
        ResolvedSource(reference, "Captured", "2026-08-17T00:00:00Z")
    )
    payload = json.loads(path.read_text())
    payload["final_uri"] = final_uri
    path.write_text(json.dumps(payload, sort_keys=True))

    loaded = store.load(reference)

    assert loaded.failure == "source_changed"
    assert loaded.detail == detail


def test_v3_snapshot_detects_valid_final_uri_tampering(tmp_path):
    reference = SourceReference("v3-tamper", "https://example.test/requested")
    store = SnapshotStore(tmp_path)
    path = store.archive(
        ResolvedSource(
            reference,
            "Captured",
            "2026-08-17T00:00:00Z",
            final_uri="https://records.example.test/final",
        )
    )
    payload = json.loads(path.read_text())
    payload["final_uri"] = "https://other.example.test/final"
    path.write_text(json.dumps(payload, sort_keys=True))

    loaded = store.load(reference)

    assert loaded.failure == "source_changed"
    assert loaded.detail == "snapshot_contract_hash_mismatch"


def test_snapshot_key_remains_requested_uri_when_final_uri_redirects(tmp_path):
    requested = "https://example.test/requested"
    final = "https://records.example.test/final"
    reference = SourceReference("redirect", requested)
    store = SnapshotStore(tmp_path)

    path = store.archive(
        ResolvedSource(reference, "Captured", "2026-08-17T00:00:00Z", final_uri=final)
    )

    assert path == store.path_for(requested)
    assert path != store.path_for(final)
    assert store.load(reference).source.final_uri == final

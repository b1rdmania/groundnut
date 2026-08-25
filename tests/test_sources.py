import json
import io
import urllib.error

from groundnut.sources import (
    EvidenceWindow,
    FileResolver,
    HttpResolver,
    ResolvedSource,
    SnapshotStore,
    SourceReference,
    SourceResolution,
    html_to_text,
)
from groundnut.provenance import sha256_text
from groundnut.verification import Claim, verify_claim


def test_file_resolver_returns_hashed_source(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Evidence text")
    result = FileResolver().resolve(SourceReference("s1", str(path)))

    assert result.ok is True
    assert result.source.text == "Evidence text"
    assert result.source.record.characters == 13
    assert result.source.evidence_window.truncation == "complete"
    assert result.source.evidence_window.original_bytes == 13


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
    assert loaded.source.evidence_window == source.evidence_window

    payload = json.loads(path.read_text())
    assert payload["schema"] == "groundnut-source-snapshot/v2"
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

    assert json.loads(path.read_text())["schema"] == "groundnut-source-failure-snapshot/v1"
    assert store.load(reference) == resolution


def test_html_to_text_ignores_script_and_decodes_entities():
    assert html_to_text(
        "<main>Revenue &amp; margin</main><script>secret()</script>"
    ) == "Revenue & margin"


class _Headers:
    def __init__(self, media_type):
        self.media_type = media_type

    def get_content_type(self):
        return self.media_type


class _Response:
    status = 200

    def __init__(self, body, media_type="text/html"):
        self.body = body
        self.headers = _Headers(media_type)

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_http_resolver_normalizes_html_without_live_network():
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(b"<p>Source <b>fact</b></p>")
    )
    result = resolver.resolve(SourceReference("web-1", "https://example.test"))

    assert result.ok is True
    assert result.source.text == "Source fact"
    assert result.source.status == 200
    assert result.source.evidence_window.truncation == "complete"
    assert result.source.evidence_window.original_bytes == len(
        b"<p>Source <b>fact</b></p>"
    )
    assert result.source.evidence_window.captured_characters == len("Source fact")


def test_http_resolver_keeps_paywall_distinct_from_unreachable():
    def paywall(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 403, "forbidden", {}, io.BytesIO()
        )

    result = HttpResolver(opener=paywall).resolve(
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
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(body, media_type="application/pdf")
    )
    result = resolver.resolve(SourceReference("pdf-1", "https://example.test/filing.pdf"))

    assert result.ok is True
    assert "Revenue was 4.2 million." in result.source.text
    assert result.source.media_type == "application/pdf"
    assert result.source.evidence_window.truncation == "complete"
    assert result.source.evidence_window.original_bytes == len(body)
    assert result.source.evidence_window.original_characters is None


def test_http_pdf_window_declares_page_limit_truncation():
    body = _pdf_bytes("Visible evidence.", "Hidden evidence after boundary.")
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(body, media_type="application/pdf"),
        max_pdf_pages=1,
    )
    result = resolver.resolve(SourceReference("pdf-window", "https://example.test/window.pdf"))

    assert result.ok is True
    assert "Visible evidence." in result.source.text
    assert "Hidden evidence" not in result.source.text
    assert result.source.evidence_window.truncation == "truncated"
    assert result.source.evidence_window.extraction_method.endswith("max_pages=1")


def test_http_resolver_reports_pdf_without_text_layer_as_unsupported():
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(out.getvalue(), media_type="application/pdf")
    )
    result = resolver.resolve(SourceReference("pdf-2", "https://example.test/scan.pdf"))

    assert result.ok is False
    assert result.failure == "pdf_unsupported"


def test_v1_snapshot_replays_with_unknown_completeness(tmp_path):
    reference = SourceReference("legacy", "https://example.test/legacy")
    text = "Legacy captured text"
    store = SnapshotStore(tmp_path / "snapshots")
    store.directory.mkdir(parents=True)
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

    loaded = store.load(reference)
    assert loaded.ok is True
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


def test_v2_snapshot_rejects_window_tampering(tmp_path):
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

import json
import io
import urllib.error

from groundnut.sources import (
    FileResolver,
    HttpResolver,
    ResolvedSource,
    SnapshotStore,
    SourceReference,
    html_to_text,
)


def test_file_resolver_returns_hashed_source(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Evidence text")
    result = FileResolver().resolve(SourceReference("s1", str(path)))

    assert result.ok is True
    assert result.source.text == "Evidence text"
    assert result.source.record.characters == 13


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

    payload = json.loads(path.read_text())
    payload["text"] = "rewritten"
    path.write_text(json.dumps(payload))
    tampered = store.load(reference)
    assert tampered.ok is False
    assert tampered.failure == "source_changed"


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


def _pdf_bytes(text: str) -> bytes:
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    # pypdf cannot lay out text; build a minimal content stream by hand.
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
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

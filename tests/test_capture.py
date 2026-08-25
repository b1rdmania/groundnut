import io
import base64
import hashlib
import json
from urllib.parse import quote, quote_plus

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from groundnut.capture import (
    CaptureDeclaration,
    ReadTimeCaptureProducer,
    canonical_reference,
    execute_request,
    validate_public_reference,
)
from groundnut.sources import (
    EvidenceWindow,
    ResolvedSource,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceReference,
    SourceResolution,
    HttpResolver,
)


HTML = "<main>Revenue reached <b>$4.2m</b>.</main>"
AUTH_SENTINEL = "GnA8_7mQ2vX9pL4cR8wK6zT1d"
COOKIE_SENTINEL = "GnA8_3hN7sB5yF9jU2eP6kV4x"
HEADER_SENTINEL = "GnA8_8rC1qW6tM3aZ9nD5sL7b"
SECRET_SENTINELS = (AUTH_SENTINEL, COOKIE_SENTINEL, HEADER_SENTINEL)


class SecretBearingResolver:
    """Fixture connector deliberately carries values canonical output must omit."""

    def __init__(self, source):
        self.source = source
        self.calls = 0
        self.request_headers = {
            "Authorization": f"Bearer {AUTH_SENTINEL}",
            "Cookie": f"session={COOKIE_SENTINEL}",
        }
        self.response_headers = {"X-Private-Session": HEADER_SENTINEL}

    def resolve(self, reference):
        self.calls += 1
        return SourceResolution(source=self.source(reference))


def _resolved(reference, text="Revenue reached $4.2m.", media_type="text/html"):
    return ResolvedSource(
        reference=reference,
        text=text,
        fetched_at="2026-08-25T12:00:00Z",
        status=200,
        media_type=media_type,
        evidence_window=EvidenceWindow.from_text(
            text,
            original_bytes=len(text.encode()),
            original_characters=len(text),
            truncation="complete",
            extraction_method="fixture-connector/v1",
        ),
    )


def _secret_forms(value):
    raw = value.encode()
    escaped = json.dumps(value)[1:-1]
    digest = hashlib.sha256(raw).hexdigest()
    return {
        value,
        value.lower(),
        value.upper(),
        quote(value, safe=""),
        quote_plus(value),
        base64.b64encode(raw).decode(),
        base64.urlsafe_b64encode(raw).decode(),
        raw.hex(),
        escaped,
        digest,
        digest[:16],
    }


def _collapsed(value):
    return "".join(character.lower() for character in value if character.isalnum())


def assert_secrets_absent(*emitted):
    combined = "\n".join(str(value) for value in emitted)
    collapsed = _collapsed(combined)
    for sentinel in SECRET_SENTINELS:
        for transformed in _secret_forms(sentinel):
            assert transformed not in combined
        assert _collapsed(sentinel) not in collapsed


def _declaration(*media_types, retained=()):
    return CaptureDeclaration(
        "public_web", tuple(media_types), retained_query_parameters=tuple(retained)
    )


def _pdf_text() -> tuple[bytes, str]:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 150 Td (PDF evidence.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), "PDF evidence."


class _Headers:
    def __init__(self, media_type):
        self.media_type = media_type
        self.private = {"X-Private-Session": HEADER_SENTINEL}

    def get_content_type(self):
        return self.media_type


class _Response:
    status = 200

    def __init__(self, body, media_type):
        self.body = body
        self.headers = _Headers(media_type)

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_declared_html_capture_replays_and_never_serializes_connector_secrets(tmp_path):
    reference = SourceReference("web-1", "https://example.test/evidence")
    connector = SecretBearingResolver(_resolved)
    store = SnapshotStore(tmp_path / "snapshots")
    producer = ReadTimeCaptureProducer(store, connector, _declaration("text/html"))

    receipt = producer.capture(reference)
    emitted = store.path_for(reference.uri).read_text() + json.dumps(receipt)

    assert receipt["acquisition"]["strategy"] == "live_archived"
    assert receipt["declaration"]["sha256"] == producer.declaration.sha256
    assert connector.calls == 1
    assert_secrets_absent(emitted)
    replay = SnapshotFirstResolver(store, mode="replay_only").acquire(reference)
    assert replay.resolution.ok is True
    assert replay.resolution.source.text == "Revenue reached $4.2m."


@pytest.mark.parametrize(
    ("body", "media_type", "expected"),
    [
        (HTML.encode(), "text/html", "Revenue reached $4.2m"),
        (_pdf_text()[0], "application/pdf", "PDF evidence."),
    ],
)
def test_http_html_and_pdf_connector_outputs_feed_snapshot_replay(
    tmp_path, body, media_type, expected
):
    resolver = HttpResolver(
        opener=lambda request, timeout: _Response(body, media_type)
    )
    reference = SourceReference("fixture", f"https://example.test/{media_type}")
    store = SnapshotStore(tmp_path)
    receipt = ReadTimeCaptureProducer(
        store, resolver, _declaration("text/html", "application/pdf")
    ).capture(reference)

    replay = SnapshotFirstResolver(store, mode="replay_only").resolve(reference)
    serialized = store.path_for(reference.uri).read_text() + json.dumps(receipt)
    assert replay.ok is True
    assert expected in replay.source.text
    assert_secrets_absent(serialized)


def test_first_read_is_frozen_and_later_capture_does_not_overwrite(tmp_path):
    reference = SourceReference("web-1", "https://example.test/evidence")
    connector = SecretBearingResolver(_resolved)
    store = SnapshotStore(tmp_path)
    producer = ReadTimeCaptureProducer(store, connector, _declaration("text/html"))

    first = producer.capture(reference)
    before = store.path_for(reference.uri).read_bytes()
    second = producer.capture(reference)

    assert connector.calls == 1
    assert store.path_for(reference.uri).read_bytes() == before
    assert first["acquisition"]["strategy"] == "live_archived"
    assert second["acquisition"]["strategy"] == "snapshot"


@pytest.mark.parametrize(
    ("media_type", "allowed", "expected_ok"),
    [("application/pdf", ("application/pdf",), True), ("image/png", ("text/html",), False)],
)
def test_non_html_capture_and_unsupported_media_are_explicit(
    tmp_path, media_type, allowed, expected_ok
):
    reference = SourceReference("source-1", "https://example.test/source")
    text = _pdf_text()[1] if media_type == "application/pdf" else "pixels"
    connector = SecretBearingResolver(
        lambda ref: _resolved(ref, text=text, media_type=media_type)
    )
    receipt = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path), connector, _declaration(*allowed)
    ).capture(reference)

    result = receipt["acquisition"]["result"]
    assert result["ok"] is expected_ok
    assert result["failure"] == (None if expected_ok else "source_media_unsupported")


def test_access_failure_remains_named_and_replayable(tmp_path):
    class Paywall:
        def resolve(self, reference):
            return SourceResolution(None, "source_paywalled", "http_403")

    reference = SourceReference("journal", "https://example.test/journal")
    store = SnapshotStore(tmp_path)
    receipt = ReadTimeCaptureProducer(
        store, Paywall(), _declaration("text/html")
    ).capture(reference)

    assert receipt["acquisition"]["result"]["failure"] == "source_paywalled"
    assert SnapshotFirstResolver(store, mode="replay_only").resolve(reference).failure == "source_paywalled"


def test_connector_exception_message_cannot_reach_artifacts_logs_or_streams(
    tmp_path, caplog, capsys
):
    class ExplodingConnector:
        def resolve(self, reference):
            raise RuntimeError(
                f"retry url={reference.uri} authorization={AUTH_SENTINEL} "
                f"cookie={COOKIE_SENTINEL} private={HEADER_SENTINEL}"
            )

    reference = SourceReference("failure", "https://example.test/failure")
    store = SnapshotStore(tmp_path)
    receipt = ReadTimeCaptureProducer(
        store, ExplodingConnector(), _declaration("text/html")
    ).capture(reference)
    streams = capsys.readouterr()
    serialized = store.path_for(reference.uri).read_text() + json.dumps(receipt)

    result = receipt["acquisition"]["result"]
    assert result["failure"] == "source_unreachable"
    assert result["detail"].startswith("connector_exception;detail_ref=sha256:")
    assert_secrets_absent(serialized, caplog.text, streams.out, streams.err)


def test_connector_failure_detail_and_undeclared_media_value_are_redacted(tmp_path):
    class LeakingFailure:
        def resolve(self, reference):
            return SourceResolution(
                None, "source_unreachable", f"retry Authorization={AUTH_SENTINEL}"
            )

    class LeakingMedia:
        def resolve(self, reference):
            return SourceResolution(
                source=_resolved(reference, media_type=f"text/{HEADER_SENTINEL}")
            )

    for name, connector in (("failure", LeakingFailure()), ("media", LeakingMedia())):
        reference = SourceReference(name, f"https://example.test/{name}")
        store = SnapshotStore(tmp_path / name)
        receipt = ReadTimeCaptureProducer(
            store, connector, _declaration("text/html")
        ).capture(reference)
        assert_secrets_absent(store.path_for(reference.uri).read_text(), json.dumps(receipt))


def test_redacted_failure_references_are_correlatable_but_not_reversible(tmp_path):
    class Failure:
        def __init__(self, detail):
            self.detail = detail

        def resolve(self, reference):
            return SourceResolution(None, "source_unreachable", self.detail)

    details = []
    for index, raw in enumerate(("novel failure A", "novel failure A", "novel failure B")):
        reference = SourceReference(f"failure-{index}", f"https://example.test/{index}")
        receipt = ReadTimeCaptureProducer(
            SnapshotStore(tmp_path / str(index)),
            Failure(raw),
            _declaration("text/html"),
        ).capture(reference)
        details.append(receipt["acquisition"]["result"]["detail"])

    assert details[0] == details[1]
    assert details[0] != details[2]
    assert all(value.startswith("connector_detail_redacted;detail_ref=sha256:") for value in details)
    assert "novel failure" not in "".join(details)


def test_query_parameters_are_default_deny_but_original_uri_is_used_for_fetch(tmp_path):
    class RecordingConnector:
        def __init__(self):
            self.uris = []

        def resolve(self, reference):
            self.uris.append(reference.uri)
            return SourceResolution(source=_resolved(reference))

    raw_uri = (
        f"https://example.test/article?article_id=42&se={COOKIE_SENTINEL}"
        f"&sp=read&sv=2026&sr=blob"
    )
    reference = SourceReference("article", raw_uri)
    connector = RecordingConnector()
    declaration = _declaration("text/html", retained=("article_id",))
    store = SnapshotStore(tmp_path)
    receipt = ReadTimeCaptureProducer(store, connector, declaration).capture(reference)
    canonical = canonical_reference(reference, declaration)

    assert connector.uris == [raw_uri]
    assert canonical.uri == "https://example.test/article?article_id=42"
    assert receipt["acquisition"]["result"]["uri"] == canonical.uri
    assert store.path_for(canonical.uri).is_file()
    assert_secrets_absent(store.path_for(canonical.uri).read_text(), json.dumps(receipt))


def test_query_parameter_retention_must_be_declared_and_noncredential_shaped():
    reference = SourceReference("article", "https://example.test/article?id=42&view=full")
    assert canonical_reference(reference, _declaration("text/html")).uri == (
        "https://example.test/article"
    )
    assert canonical_reference(
        reference, _declaration("text/html", retained=("id",))
    ).uri == "https://example.test/article?id=42"
    with pytest.raises(ValueError, match="cannot be retained"):
        _declaration("text/html", retained=("access_token",))


@pytest.mark.parametrize(
    "uri",
    [
        "https://user:password@example.test/source",
        "https://example.test/auth/credential/source",
        "file:///private/report.html",
    ],
)
def test_credential_bearing_or_non_http_source_identity_is_rejected(uri):
    with pytest.raises(ValueError) as caught:
        validate_public_reference(SourceReference("unsafe", uri))
    assert_secrets_absent(str(caught.value))


def test_capture_request_requires_explicit_live_authority(tmp_path):
    request = {
        "schema": "groundnut-read-capture-request/v2",
        "snapshot_directory": "snapshots",
        "declaration": {
            "connector": "public_web",
            "intent": "evidence_verification",
            "media_types": ["text/html", "application/pdf"],
            "retained_query_parameters": [],
        },
        "sources": [{"source_id": "web-1", "uri": "https://example.test"}],
    }
    with pytest.raises(ValueError, match="--allow-live"):
        execute_request(request, base_directory=tmp_path, allow_live=False)

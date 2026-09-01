import io
import base64
import hashlib
import json
import subprocess
import sys
from urllib.parse import quote, quote_plus

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from groundnut.capture import (
    CaptureDeclaration,
    ReadTimeCaptureProducer,
    canonical_reference,
    execute_request,
    query_policy_application,
    validate_capture_receipt,
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


def _rehash_receipt(receipt):
    payload = {key: value for key, value in receipt.items() if key != "sha256"}
    receipt["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return receipt


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

    def get(self, name, default=None):
        return default


class _Response:
    status = 200

    def __init__(self, body, media_type):
        self.body = body
        self.headers = _Headers(media_type)

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

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
        opener=lambda request, timeout: _Response(body, media_type),
        address_resolver=lambda hostname, port: ("93.184.216.34",),
        allow_injected_transport=True,
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


def test_capture_rejects_distinct_public_urls_collapsing_to_one_snapshot(tmp_path):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    store = SnapshotStore(tmp_path)
    producer = ReadTimeCaptureProducer(store, Connector(), _declaration("text/html"))
    producer.capture(SourceReference("a", "https://example.test/article?id=A"))

    with pytest.raises(ValueError, match="record-bearing query parameter"):
        ReadTimeCaptureProducer(
            store, Connector(), _declaration("text/html")
        ).capture(SourceReference("b", "https://example.test/article?id=B"))


def test_capture_allows_secret_rotation_for_one_public_identity(tmp_path):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    producer = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path), Connector(), _declaration("text/html")
    )
    first = producer.capture(
        SourceReference("a", "https://example.test/article?access_token=one")
    )
    second = producer.capture(
        SourceReference("b", "https://example.test/article?access_token=two")
    )

    assert first["acquisition"]["result"]["uri"] == second["acquisition"]["result"]["uri"]


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


def test_v3_query_retention_is_exact_host_specific_and_normalises_uri_host_case():
    declaration = CaptureDeclaration(
        "public_web",
        ("text/html",),
        retained_query_parameters_by_host={"journals.plos.org": ("id",)},
    )
    retained = canonical_reference(
        SourceReference("plos", "https://JOURNALS.PLOS.ORG/article?id=10&view=full#part"),
        declaration,
    )
    dropped = canonical_reference(
        SourceReference("other", "https://example.test/article?id=10"), declaration
    )
    assert retained.uri == "https://journals.plos.org/article?id=10"
    assert dropped.uri == "https://example.test/article"
    with pytest.raises(ValueError, match="lower-case"):
        CaptureDeclaration(
            "public_web",
            ("text/html",),
            retained_query_parameters_by_host={"Journals.Plos.org": ("id",)},
        )


def test_v2_and_v3_canonical_identity_share_host_and_blank_query_normalisation():
    reference = SourceReference(
        "article", "HTTPS://Example.COM/article?id=&view=full#part"
    )
    v2 = CaptureDeclaration(
        "public_web", ("text/html",), retained_query_parameters=("id",)
    )
    v3 = CaptureDeclaration(
        "public_web",
        ("text/html",),
        retained_query_parameters_by_host={"example.com": ("id",)},
    )

    assert canonical_reference(reference, v2).uri == (
        "https://example.com/article?id="
    )
    assert canonical_reference(reference, v3).uri == (
        "https://example.com/article?id="
    )
    assert query_policy_application(reference, v2)["keys_retained"] == ["id"]


def test_v3_receipt_exposes_query_policy_without_values_or_sensitive_names(tmp_path):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    declaration = CaptureDeclaration(
        "public_web",
        ("text/html",),
        retained_query_parameters_by_host={"api.nsf.gov": ("AWD_ID",)},
    )
    reference = SourceReference(
        "award",
        f"https://api.nsf.gov/award?AWD_ID=1234&view=full&access_token={AUTH_SENTINEL}#fragment",
    )
    receipt = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path), Connector(), declaration
    ).capture(reference)
    policy = receipt["query_policy_application"]
    assert policy == {
        "schema": "groundnut-query-policy-application/v1",
        "host": "api.nsf.gov",
        "keys_present": ["AWD_ID", "view"],
        "keys_retained": ["AWD_ID"],
        "non_sensitive_keys_dropped": ["view"],
        "credential_shaped_keys_dropped_count": 1,
    }
    policy_serialized = json.dumps(policy)
    assert "1234" not in policy_serialized
    assert "access_token" not in policy_serialized
    assert "fragment" not in receipt["acquisition"]["result"]["uri"]
    validate_capture_receipt(receipt)
    receipt["query_policy_application"]["keys_retained"] = []
    with pytest.raises(ValueError, match="receipt sha256"):
        validate_capture_receipt(receipt)


def test_v2_receipt_replay_preserves_absence_of_query_policy_metadata(tmp_path):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    receipt = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path),
        Connector(),
        _declaration("text/html", retained=("id",)),
    ).capture(SourceReference("article", "https://example.test/article?id=42"))
    serialized = json.dumps(receipt, sort_keys=True, separators=(",", ":"))

    assert "query_policy_application" not in receipt
    assert validate_capture_receipt(receipt) == receipt
    assert json.dumps(receipt, sort_keys=True, separators=(",", ":")) == serialized


def test_v3_receipt_with_hash_consistent_missing_query_policy_fails(tmp_path):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    declaration = CaptureDeclaration(
        "public_web",
        ("text/html",),
        retained_query_parameters_by_host={"example.test": ("id",)},
    )
    receipt = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path), Connector(), declaration
    ).capture(SourceReference("article", "https://example.test/article?id=42"))
    receipt.pop("query_policy_application")
    _rehash_receipt(receipt)

    with pytest.raises(ValueError, match="requires query_policy_application"):
        validate_capture_receipt(receipt)


def test_v2_receipt_with_hash_consistent_query_policy_metadata_fails(tmp_path):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    receipt = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path), Connector(), _declaration("text/html")
    ).capture(SourceReference("article", "https://example.test/article"))
    receipt["query_policy_application"] = {
        "schema": "groundnut-query-policy-application/v1",
        "host": "example.test",
        "keys_present": [],
        "keys_retained": [],
        "non_sensitive_keys_dropped": [],
        "credential_shaped_keys_dropped_count": 0,
    }
    _rehash_receipt(receipt)

    with pytest.raises(ValueError, match="v2 capture receipt must not contain"):
        validate_capture_receipt(receipt)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda policy: policy.update({"query_values": {"id": "42"}}),
        lambda policy: policy.__setitem__("schema", "groundnut-query-policy-application/v2"),
        lambda policy: policy.__setitem__("host", "other.test"),
        lambda policy: policy.__setitem__("keys_present", "id"),
        lambda policy: policy.__setitem__("keys_present", ["id", "id"]),
        lambda policy: policy.__setitem__("keys_retained", ["missing"]),
        lambda policy: policy.__setitem__("non_sensitive_keys_dropped", ["missing"]),
        lambda policy: policy.__setitem__("non_sensitive_keys_dropped", ["id"]),
        lambda policy: policy.__setitem__("credential_shaped_keys_dropped_count", -1),
        lambda policy: policy.__setitem__("credential_shaped_keys_dropped_count", True),
    ],
)
def test_v3_receipt_with_hash_consistent_malformed_query_policy_fails(
    tmp_path, mutate
):
    class Connector:
        def resolve(self, reference):
            return SourceResolution(source=_resolved(reference))

    declaration = CaptureDeclaration(
        "public_web",
        ("text/html",),
        retained_query_parameters_by_host={"example.test": ("id",)},
    )
    receipt = ReadTimeCaptureProducer(
        SnapshotStore(tmp_path), Connector(), declaration
    ).capture(
        SourceReference(
            "article",
            f"https://example.test/article?id=42&view=full&access_token={AUTH_SENTINEL}",
        )
    )

    mutate(receipt["query_policy_application"])
    _rehash_receipt(receipt)

    with pytest.raises(ValueError):
        validate_capture_receipt(receipt)


def test_v2_declaration_replay_is_byte_identical_and_hash_validated():
    original = _declaration("text/html", retained=("id",)).to_dict()
    replayed = CaptureDeclaration.from_mapping(original).to_dict()
    assert json.dumps(replayed, sort_keys=True, separators=(",", ":")) == json.dumps(
        original, sort_keys=True, separators=(",", ":")
    )
    tampered = dict(original)
    tampered["retained_query_parameters"] = []
    with pytest.raises(ValueError, match="sha256"):
        CaptureDeclaration.from_mapping(tampered)


def test_v3_declaration_rejects_credential_shaped_retainable_name():
    with pytest.raises(ValueError, match="cannot be retained"):
        CaptureDeclaration(
            "public_web",
            ("text/html",),
            retained_query_parameters_by_host={"example.test": ("session_key",)},
        )


def test_v3_declaration_tampering_fails_its_own_hash():
    serialized = CaptureDeclaration(
        "public_web",
        ("text/html",),
        retained_query_parameters_by_host={"journals.plos.org": ("id",)},
    ).to_dict()
    serialized["retained_query_parameters_by_host"] = {
        "journals.plos.org": ["id", "article"]
    }
    with pytest.raises(ValueError, match="sha256"):
        CaptureDeclaration.from_mapping(serialized)


@pytest.mark.parametrize(
    "uri",
    [
        "https://user:password@example.test/source",
        "file:///private/report.html",
    ],
)
def test_credential_bearing_or_non_http_source_identity_is_rejected(uri):
    with pytest.raises(ValueError) as caught:
        validate_public_reference(SourceReference("unsafe", uri))
    assert_secrets_absent(str(caught.value))


@pytest.mark.parametrize(
    "path",
    ["key-findings", "market-signature-analysis", "session-2"],
)
def test_public_path_words_are_not_mistaken_for_credentials(path):
    reference = SourceReference("public", f"https://example.test/{path}")
    assert canonical_reference(reference, _declaration("text/html")) == reference


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


def test_capture_module_entry_point_exposes_help():
    completed = subprocess.run(
        [sys.executable, "-m", "groundnut.capture", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Capture declared source reads" in completed.stdout

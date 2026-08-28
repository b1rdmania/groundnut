import json

import pytest

from groundnut.capture import CaptureDeclaration, resolve_snapshot
from groundnut.sources import (
    EvidenceWindow,
    ResolvedSource,
    SnapshotStore,
    SourceReference,
    SourceResolution,
)


def declaration():
    return CaptureDeclaration(
        "public_web",
        ("text/html", "text/plain"),
        retained_query_parameters_by_host={
            "journals.plos.org": ("id",),
            "api.nsf.gov": ("AWD_ID",),
        },
    )


def source(reference, text="Usable recorded evidence.", *, truncation="complete", status=200):
    return ResolvedSource(
        reference=reference,
        text=text,
        fetched_at="2026-08-28T00:00:00Z",
        status=status,
        media_type="text/html",
        evidence_window=EvidenceWindow.from_text(
            text,
            truncation=truncation,
            extraction_method="fixture/v1",
            original_bytes=len(text.encode()),
            original_characters=len(text),
        ),
    )


def test_raw_query_resolves_one_canonical_snapshot_and_keeps_both_identities(tmp_path):
    raw = SourceReference(
        "citation", "https://example.test/article?tracking=1#section"
    )
    canonical = SourceReference("capture", "https://example.test/article")
    store = SnapshotStore(tmp_path)
    store.archive(source(canonical))

    result = resolve_snapshot(raw, declaration(), store)

    assert result.ok
    assert result.raw_reference == raw
    assert result.canonical_reference.uri == canonical.uri
    assert result.source.reference.source_id == raw.source_id
    assert result.snapshot_path == str(store.path_for(canonical.uri))
    assert result.to_dict()["canonical_identity"]["uri"] == canonical.uri


def test_approved_record_key_resolves_record_specific_snapshot(tmp_path):
    raw = SourceReference(
        "award", "https://API.NSF.GOV/award?AWD_ID=1234&tracking=x"
    )
    canonical_uri = "https://api.nsf.gov/award?AWD_ID=1234"
    store = SnapshotStore(tmp_path)
    store.archive(source(SourceReference("captured", canonical_uri)))

    result = resolve_snapshot(raw, declaration(), store)

    assert result.ok
    assert result.canonical_reference.uri == canonical_uri


@pytest.mark.parametrize(
    ("truncation", "text", "failure"),
    [
        ("empty", "", "empty_text"),
        ("sparse", "Sparse shell", "incomplete_evidence_window"),
        ("truncated", "Partial record", "incomplete_evidence_window"),
        ("unknown", "Legacy record", "incomplete_evidence_window"),
        ("hollow", "Verify you are human", "hollow_capture"),
    ],
)
def test_unusable_windows_return_typed_failure_at_canonical_identity(
    tmp_path, truncation, text, failure
):
    raw = SourceReference("record", "https://example.test/record?drop=1")
    canonical = SourceReference("captured", "https://example.test/record")
    store = SnapshotStore(tmp_path)
    store.archive(source(canonical, text, truncation=truncation))

    result = resolve_snapshot(raw, declaration(), store)

    assert result.failure == failure
    assert result.canonical_reference.uri == canonical.uri
    assert result.source is None


def test_missing_http_failure_and_corrupt_snapshot_fail_closed(tmp_path):
    reference = SourceReference("record", "https://example.test/record")
    store = SnapshotStore(tmp_path)
    assert resolve_snapshot(reference, declaration(), store).failure == "snapshot_missing"

    store.archive_failure(
        reference,
        SourceResolution(None, "source_paywalled", "http_403"),
    )
    assert resolve_snapshot(reference, declaration(), store).failure == "http_status"

    store = SnapshotStore(tmp_path / "corrupt")
    path = store.archive(source(reference))
    payload = json.loads(path.read_text())
    payload["uri"] = "https://wrong.test/identity"
    path.write_text(json.dumps(payload))
    corrupted = resolve_snapshot(reference, declaration(), store)
    assert corrupted.failure == "source_changed"
    assert corrupted.detail == "snapshot_identity_mismatch"


def test_non_success_status_is_typed_http_status(tmp_path):
    reference = SourceReference("record", "https://example.test/record")
    store = SnapshotStore(tmp_path)
    store.archive(source(reference, status=503))
    result = resolve_snapshot(reference, declaration(), store)
    assert result.failure == "http_status"
    assert result.detail == "http_503"


def test_resolver_api_has_no_live_resolver_or_fallback_parameter():
    import inspect

    assert tuple(inspect.signature(resolve_snapshot).parameters) == (
        "reference",
        "declaration",
        "store",
    )

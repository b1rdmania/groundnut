import json

import pytest

from groundnut.sources import (
    EvidenceWindow,
    ResolvedSource,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceReference,
    SourceResolution,
)
from groundnut.verification import Claim, verify_claim


REFERENCE = SourceReference("source-1", "https://example.test/source")


class FakeResolver:
    def __init__(self, resolution):
        self.resolution = resolution
        self.calls = 0

    def resolve(self, reference):
        self.calls += 1
        return self.resolution


def resolved(text="frozen source text"):
    return SourceResolution(
        source=ResolvedSource(
            reference=REFERENCE,
            text=text,
            fetched_at="2026-08-17T00:00:00Z",
            status=200,
            media_type="text/plain",
        )
    )


def test_replay_only_never_calls_live_and_reports_missing_snapshot(tmp_path):
    live = FakeResolver(resolved())
    resolver = SnapshotFirstResolver(SnapshotStore(tmp_path), live, mode="replay_only")
    result = resolver.acquire(REFERENCE)
    assert result.strategy == "snapshot_missing"
    assert result.mode == "replay_only"
    assert result.resolution.detail == "snapshot_missing"
    assert result.live_attempted is False
    assert live.calls == 0


def test_snapshot_preferred_archives_once_then_replays_without_live(tmp_path):
    live = FakeResolver(resolved())
    resolver = SnapshotFirstResolver(
        SnapshotStore(tmp_path), live, mode="snapshot_preferred"
    )
    first = resolver.acquire(REFERENCE)
    second = resolver.acquire(REFERENCE)
    assert first.strategy == "live_archived"
    assert first.mode == "snapshot_preferred"
    assert second.strategy == "snapshot"
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert second.resolution.source.text == "frozen source text"
    assert live.calls == 1
    assert second.to_dict()["schema"] == "groundnut-source-acquisition/v3"
    assert second.to_dict()["result"]["evidence_window"]["sha256"]
    assert second.to_dict()["result"]["final_uri"] == REFERENCE.uri


def test_snapshot_joins_on_uri_when_host_source_id_differs(tmp_path):
    host_reference = SourceReference("host-chosen-slug", REFERENCE.uri)
    host_source = ResolvedSource(
        reference=host_reference,
        text="frozen source text",
        fetched_at="2026-08-17T00:00:00Z",
    )
    store = SnapshotStore(tmp_path)
    store.archive(host_source)

    replay = SnapshotFirstResolver(store, mode="replay_only").acquire(REFERENCE)

    assert replay.strategy == "snapshot"
    assert replay.resolution.ok
    assert replay.resolution.source.reference == REFERENCE
    assert replay.resolution.source.text == "frozen source text"


def test_cross_phase_capture_replays_same_uri_under_a_new_source_id(tmp_path):
    first_reference = SourceReference("phase-1-slug", REFERENCE.uri)
    live = FakeResolver(
        SourceResolution(
            source=ResolvedSource(
                reference=first_reference,
                text="first read stays frozen",
                fetched_at="2026-08-17T00:00:00Z",
            )
        )
    )
    store = SnapshotStore(tmp_path)
    first = SnapshotFirstResolver(store, live, mode="snapshot_preferred").acquire(
        first_reference
    )
    second_reference = SourceReference("phase-2-slug", REFERENCE.uri)
    second = SnapshotFirstResolver(store, live, mode="snapshot_preferred").acquire(
        second_reference
    )

    assert first.strategy == "live_archived"
    assert second.strategy == "snapshot"
    assert second.resolution.source.reference == second_reference
    assert second.resolution.source.text == "first read stays frozen"
    assert live.calls == 1


def test_snapshot_preferred_archives_failure_taxonomy_for_replay(tmp_path):
    failure = SourceResolution(
        source=None, failure="source_paywalled", detail="http_403"
    )
    live = FakeResolver(failure)
    store = SnapshotStore(tmp_path)
    first = SnapshotFirstResolver(store, live, mode="snapshot_preferred").acquire(
        REFERENCE
    )
    replay = SnapshotFirstResolver(store, mode="replay_only").acquire(REFERENCE)

    assert first.strategy == "live_failed_archived"
    assert first.snapshot_sha256 == replay.snapshot_sha256
    assert replay.strategy == "snapshot"
    assert replay.resolution == failure
    assert replay.live_attempted is False
    assert live.calls == 1


def test_replay_preserves_truncated_window_and_verification_classification(tmp_path):
    captured = "Permit issued before the capture boundary."
    source = ResolvedSource(
        reference=REFERENCE,
        text=captured,
        fetched_at="2026-08-17T00:00:00Z",
        evidence_window=EvidenceWindow.from_text(
            captured,
            original_bytes=100,
            original_characters=100,
            truncation="truncated",
            extraction_method="boundary-fixture/v1",
        ),
    )
    live = FakeResolver(SourceResolution(source=source))
    store = SnapshotStore(tmp_path)
    first = SnapshotFirstResolver(store, live, mode="snapshot_preferred").acquire(
        REFERENCE
    )
    replay = SnapshotFirstResolver(store, mode="replay_only").acquire(REFERENCE)
    claim = Claim(
        "after-boundary",
        "Renewal occurs later.",
        source=REFERENCE,
        excerpt="Renewal deadline is after the capture boundary.",
    )

    live_result = verify_claim(claim, first.resolution)
    replay_result = verify_claim(claim, replay.resolution)

    assert live_result.to_dict() == replay_result.to_dict()
    assert replay_result.outcome == "evidence_window_incomplete"
    assert (
        first.resolution.source.evidence_window.sha256
        == replay.resolution.source.evidence_window.sha256
    )


def test_tampered_failure_snapshot_fails_closed(tmp_path):
    store = SnapshotStore(tmp_path)
    store.archive_failure(
        REFERENCE,
        SourceResolution(source=None, failure="source_paywalled", detail="http_403"),
    )
    payload = json.loads(store.path_for(REFERENCE.uri).read_text())
    payload["failure"] = "truth_unknown"
    store.path_for(REFERENCE.uri).write_text(json.dumps(payload))

    replay = SnapshotFirstResolver(store, mode="replay_only").acquire(REFERENCE)
    assert replay.strategy == "snapshot_invalid"
    assert replay.resolution.failure == "source_changed"
    assert replay.resolution.detail == "snapshot_failure_invalid"


def test_invalid_existing_snapshot_fails_closed_without_live_fallback(tmp_path):
    store = SnapshotStore(tmp_path)
    store.archive(resolved().source)
    payload = json.loads(store.path_for(REFERENCE.uri).read_text())
    payload["text"] = "tampered"
    store.path_for(REFERENCE.uri).write_text(json.dumps(payload))
    live = FakeResolver(resolved("new live text"))
    result = SnapshotFirstResolver(store, live, mode="snapshot_preferred").acquire(
        REFERENCE
    )
    assert result.strategy == "snapshot_invalid"
    assert result.resolution.failure == "source_changed"
    assert live.calls == 0


def test_explicit_refresh_replaces_snapshot_only_after_live_success(tmp_path):
    store = SnapshotStore(tmp_path)
    path = store.archive(resolved("old text").source)
    before = path.read_bytes()
    live = FakeResolver(resolved("new text"))
    result = SnapshotFirstResolver(store, live, mode="refresh").acquire(REFERENCE)
    assert result.strategy == "live_archived"
    assert store.load(REFERENCE).source.text == "new text"
    assert path.read_bytes() != before


def test_failed_refresh_preserves_existing_snapshot(tmp_path):
    store = SnapshotStore(tmp_path)
    path = store.archive(resolved("old text").source)
    before = path.read_bytes()
    live = FakeResolver(
        SourceResolution(
            source=None, failure="source_unreachable", detail="fixture_failure"
        )
    )
    result = SnapshotFirstResolver(store, live, mode="refresh").acquire(REFERENCE)
    assert result.strategy == "live_failed"
    assert path.read_bytes() == before
    assert store.load(REFERENCE).source.text == "old text"


def test_live_modes_require_resolver_and_unknown_mode_is_rejected(tmp_path):
    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError, match="requires a live resolver"):
        SnapshotFirstResolver(store, mode="snapshot_preferred")
    with pytest.raises(ValueError, match="unknown snapshot-first mode"):
        SnapshotFirstResolver(store, mode="invented")

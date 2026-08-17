import json

import pytest

from groundnut.sources import (
    ResolvedSource,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceReference,
    SourceResolution,
)


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
    assert second.to_dict()["schema"] == "groundnut-source-acquisition/v1"


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

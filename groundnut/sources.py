"""Source acquisition and snapshot adapters.

Extraction begins with normalized source text, but provenance starts one stage
earlier. Resolvers make acquisition explicit and preserve honest failure states
instead of turning paywalls, unreachable pages, or unsupported PDFs into an
empty source. Snapshots pin what the engine actually saw.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import hashlib
from pathlib import Path
from typing import Callable, Protocol
import urllib.error
import urllib.request

from .provenance import SourceRecord, sha256_text


FAILURE_STATES = {
    "source_paywalled",
    "source_unreachable",
    "source_changed",
    "pdf_unsupported",
}


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    uri: str


@dataclass(frozen=True)
class ResolvedSource:
    reference: SourceReference
    text: str
    fetched_at: str
    status: int | None = None
    media_type: str | None = None

    @property
    def record(self) -> SourceRecord:
        return SourceRecord.from_text(self.reference.source_id, self.text)


@dataclass(frozen=True)
class SourceResolution:
    source: ResolvedSource | None
    failure: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if (self.source is None) == (self.failure is None):
            raise ValueError("resolution must contain exactly one of source or failure")
        if self.failure is not None and self.failure not in FAILURE_STATES:
            raise ValueError(f"unknown source failure: {self.failure}")

    @property
    def ok(self) -> bool:
        return self.source is not None


class SourceResolver(Protocol):
    def resolve(self, reference: SourceReference) -> SourceResolution: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileResolver:
    def resolve(self, reference: SourceReference) -> SourceResolution:
        path = Path(reference.uri).expanduser()
        try:
            text = path.read_text(errors="replace")
        except OSError as exc:
            return SourceResolution(
                source=None, failure="source_unreachable", detail=type(exc).__name__
            )
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=_now(),
                media_type="text/plain",
            )
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored += 1

    def handle_endtag(self, tag) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data) -> None:
        if not self._ignored:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return parser.text()


def default_opener() -> Callable:
    """urlopen with a certifi CA bundle when one is installed.

    Some Python builds ship without a usable system trust store and fail every
    HTTPS fetch with ``CERTIFICATE_VERIFY_FAILED``; the ledger then reports
    every source as unreachable, which is a tooling fact, not an evidence fact.
    """
    try:
        import certifi
    except ImportError:  # pragma: no cover - depends on the host environment
        return urllib.request.urlopen
    import ssl

    context = ssl.create_default_context(cafile=certifi.where())

    def opener(request, *, timeout):
        return urllib.request.urlopen(request, timeout=timeout, context=context)

    return opener


class HttpResolver:
    """Small standard-library HTTP adapter; no provider credentials involved."""

    def __init__(
        self,
        *,
        timeout: int = 20,
        opener: Callable | None = None,
    ) -> None:
        self.timeout = timeout
        self.opener = opener or default_opener()

    def resolve(self, reference: SourceReference) -> SourceResolution:
        request = urllib.request.Request(
            reference.uri,
            headers={
                "User-Agent": "groundnut/0.1 source-verification",
                "Accept": "text/html,text/plain,application/pdf;q=0.5,*/*;q=0.1",
            },
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                media_type = response.headers.get_content_type()
                if media_type == "application/pdf":
                    return SourceResolution(
                        source=None,
                        failure="pdf_unsupported",
                        detail="application/pdf",
                    )
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            failure = (
                "source_paywalled"
                if exc.code in {401, 402, 403, 429}
                else "source_unreachable"
            )
            return SourceResolution(
                source=None, failure=failure, detail=f"http_{exc.code}"
            )
        except (OSError, urllib.error.URLError) as exc:
            return SourceResolution(
                source=None, failure="source_unreachable", detail=type(exc).__name__
            )
        text = html_to_text(raw) if media_type in {"text/html", "application/xhtml+xml"} else raw
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=_now(),
                status=status,
                media_type=media_type,
            )
        )


class SnapshotStore:
    """JSON source archive keyed by URI hash and verified when reopened."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    @staticmethod
    def key(uri: str) -> str:
        return sha256_text(uri)[:24]

    def path_for(self, uri: str) -> Path:
        return self.directory / f"{self.key(uri)}.json"

    def contains(self, reference: SourceReference) -> bool:
        return self.path_for(reference.uri).is_file()

    def archive(self, source: ResolvedSource) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(source.reference.uri)
        payload = {
            "schema": "groundnut-source-snapshot/v1",
            "source_id": source.reference.source_id,
            "uri": source.reference.uri,
            "fetched_at": source.fetched_at,
            "status": source.status,
            "media_type": source.media_type,
            "sha256": sha256_text(source.text),
            "text": source.text,
        }
        path.write_text(json.dumps(payload, sort_keys=True))
        return path

    def load(self, reference: SourceReference) -> SourceResolution:
        path = self.path_for(reference.uri)
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return SourceResolution(
                source=None, failure="source_unreachable", detail=type(exc).__name__
            )
        if (
            value.get("schema") != "groundnut-source-snapshot/v1"
            or value.get("uri") != reference.uri
            or value.get("source_id") != reference.source_id
        ):
            return SourceResolution(
                source=None, failure="source_changed", detail="snapshot_identity_mismatch"
            )
        text = value.get("text")
        if not isinstance(text, str) or sha256_text(text) != value.get("sha256"):
            return SourceResolution(
                source=None, failure="source_changed", detail="snapshot_hash_mismatch"
            )
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=str(value["fetched_at"]),
                status=value.get("status"),
                media_type=value.get("media_type"),
            )
        )


@dataclass(frozen=True)
class SourceAcquisition:
    reference: SourceReference
    resolution: SourceResolution
    mode: str
    strategy: str
    snapshot_sha256: str | None
    live_attempted: bool

    def __post_init__(self) -> None:
        if self.mode not in SnapshotFirstResolver.MODES:
            raise ValueError(f"unknown source acquisition mode: {self.mode}")
        if self.strategy not in {"snapshot", "live_archived", "live_failed", "snapshot_missing", "snapshot_invalid"}:
            raise ValueError(f"unknown source acquisition strategy: {self.strategy}")

    def to_dict(self) -> dict:
        source = self.resolution.source
        return {
            "schema": "groundnut-source-acquisition/v1",
            "mode": self.mode,
            "strategy": self.strategy,
            "snapshot_sha256": self.snapshot_sha256,
            "live_attempted": self.live_attempted,
            "result": {
                "ok": self.resolution.ok,
                "source_id": self.reference.source_id,
                "uri": self.reference.uri,
                "source_sha256": source.record.sha256 if source else None,
                "failure": self.resolution.failure,
                "detail": self.resolution.detail,
            },
        }


class SnapshotFirstResolver:
    """Explicit replay-first orchestration over a snapshot store and resolver.

    `replay_only` never invokes the live resolver. `snapshot_preferred` invokes
    it only when no snapshot exists and archives a successful result. A present
    but invalid snapshot fails closed instead of being hidden by a live fetch.
    `refresh` explicitly bypasses an existing snapshot and replaces it only
    after a successful live resolution.
    """

    MODES = {"replay_only", "snapshot_preferred", "refresh"}

    def __init__(
        self,
        snapshots: SnapshotStore,
        live: SourceResolver | None = None,
        *,
        mode: str = "replay_only",
    ) -> None:
        if mode not in self.MODES:
            raise ValueError(f"unknown snapshot-first mode: {mode}")
        if mode != "replay_only" and live is None:
            raise ValueError(f"{mode} mode requires a live resolver")
        self.snapshots = snapshots
        self.live = live
        self.mode = mode

    def acquire(self, reference: SourceReference) -> SourceAcquisition:
        exists = self.snapshots.contains(reference)
        if self.mode != "refresh" and exists:
            resolution = self.snapshots.load(reference)
            return SourceAcquisition(
                reference=reference,
                resolution=resolution,
                mode=self.mode,
                strategy="snapshot" if resolution.ok else "snapshot_invalid",
                snapshot_sha256=_file_sha256(self.snapshots.path_for(reference.uri)),
                live_attempted=False,
            )
        if self.mode == "replay_only":
            return SourceAcquisition(
                reference=reference,
                resolution=SourceResolution(
                    source=None,
                    failure="source_unreachable",
                    detail="snapshot_missing",
                ),
                mode=self.mode,
                strategy="snapshot_missing",
                snapshot_sha256=None,
                live_attempted=False,
            )
        assert self.live is not None
        resolution = self.live.resolve(reference)
        if not resolution.ok:
            return SourceAcquisition(
                reference=reference,
                resolution=resolution,
                mode=self.mode,
                strategy="live_failed",
                snapshot_sha256=(
                    _file_sha256(self.snapshots.path_for(reference.uri))
                    if exists
                    else None
                ),
                live_attempted=True,
            )
        path = self.snapshots.archive(resolution.source)
        return SourceAcquisition(
            reference=reference,
            resolution=resolution,
            mode=self.mode,
            strategy="live_archived",
            snapshot_sha256=_file_sha256(path),
            live_attempted=True,
        )

    def resolve(self, reference: SourceReference) -> SourceResolution:
        return self.acquire(reference).resolution


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

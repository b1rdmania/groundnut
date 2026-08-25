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
import io
import json
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.request

from .provenance import SourceRecord, sha256_text


FAILURE_STATES = {
    "source_paywalled",
    "source_unreachable",
    "source_changed",
    "pdf_unsupported",
    "source_media_unsupported",
}


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    uri: str


@dataclass(frozen=True)
class EvidenceWindow:
    """Identity and completeness of the exact text searched by verification."""

    captured_bytes: int
    captured_characters: int
    truncation: str
    extraction_method: str
    text_sha256: str
    original_bytes: int | None = None
    original_characters: int | None = None

    TRUNCATION_STATES = {"complete", "truncated", "unknown"}

    def __post_init__(self) -> None:
        lengths = (
            self.captured_bytes,
            self.captured_characters,
            self.original_bytes,
            self.original_characters,
        )
        if any(value is not None and value < 0 for value in lengths):
            raise ValueError("evidence-window lengths must not be negative")
        if self.truncation not in self.TRUNCATION_STATES:
            raise ValueError(f"unknown evidence-window truncation: {self.truncation}")
        if not self.extraction_method.strip():
            raise ValueError("evidence-window extraction method is required")
        if len(self.text_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.text_sha256
        ):
            raise ValueError("evidence-window text_sha256 must be lowercase SHA-256")

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        truncation: str,
        extraction_method: str,
        original_bytes: int | None = None,
        original_characters: int | None = None,
    ) -> "EvidenceWindow":
        return cls(
            original_bytes=original_bytes,
            original_characters=original_characters,
            captured_bytes=len(text.encode()),
            captured_characters=len(text),
            truncation=truncation,
            extraction_method=extraction_method,
            text_sha256=sha256_text(text),
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-evidence-window/v1",
            "original_bytes": self.original_bytes,
            "original_characters": self.original_characters,
            "captured_bytes": self.captured_bytes,
            "captured_characters": self.captured_characters,
            "truncation": self.truncation,
            "extraction_method": self.extraction_method,
            "text_sha256": self.text_sha256,
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, text: str) -> "EvidenceWindow":
        if not isinstance(value, Mapping):
            raise ValueError("evidence window must be an object")
        if value.get("schema") != "groundnut-evidence-window/v1":
            raise ValueError("unsupported evidence-window schema")
        window = cls(
            original_bytes=_optional_int(value.get("original_bytes")),
            original_characters=_optional_int(value.get("original_characters")),
            captured_bytes=_required_int(value.get("captured_bytes")),
            captured_characters=_required_int(value.get("captured_characters")),
            truncation=str(value.get("truncation")),
            extraction_method=str(value.get("extraction_method")),
            text_sha256=str(value.get("text_sha256")),
        )
        expected = cls.from_text(
            text,
            truncation=window.truncation,
            extraction_method=window.extraction_method,
            original_bytes=window.original_bytes,
            original_characters=window.original_characters,
        )
        if window != expected:
            raise ValueError("evidence window does not match captured text")
        if value.get("sha256") != window.sha256:
            raise ValueError("evidence-window sha256 does not match its content")
        return window


@dataclass(frozen=True)
class ResolvedSource:
    reference: SourceReference
    text: str
    fetched_at: str
    status: int | None = None
    media_type: str | None = None
    evidence_window: EvidenceWindow | None = None

    def __post_init__(self) -> None:
        window = self.evidence_window or EvidenceWindow.from_text(
            self.text,
            truncation="unknown",
            extraction_method="unspecified-resolver/v1",
        )
        if (
            window.captured_bytes != len(self.text.encode())
            or window.captured_characters != len(self.text)
            or window.text_sha256 != sha256_text(self.text)
        ):
            raise ValueError("resolved source evidence window does not match its text")
        object.__setattr__(self, "evidence_window", window)

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
            raw = path.read_bytes()
        except OSError as exc:
            return SourceResolution(
                source=None, failure="source_unreachable", detail=type(exc).__name__
            )
        text = raw.decode("utf-8", errors="replace")
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=_now(),
                media_type="text/plain",
                evidence_window=EvidenceWindow.from_text(
                    text,
                    original_bytes=len(raw),
                    original_characters=len(text),
                    truncation="complete",
                    extraction_method="file:utf-8-errors-replace/v1",
                ),
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


def _pdf_to_text_and_pages(
    data: bytes, *, max_pages: int = 400
) -> tuple[str | None, int | None]:
    """Text layer of a PDF via pypdf, page-joined; None when unavailable.

    Scanned PDFs with no text layer return None rather than an empty source,
    so the claim is reported as pdf_unsupported instead of not_found.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - depends on the host environment
        return None, None
    try:
        reader = PdfReader(io.BytesIO(data))
        total_pages = len(reader.pages)
        pages = [page.extract_text() or "" for page in reader.pages[:max_pages]]
    except Exception:  # pypdf raises a wide family on malformed files
        return None, None
    text = "\n\n".join(page.strip() for page in pages)
    return (text if text.strip() else None), total_pages


def pdf_to_text(data: bytes, *, max_pages: int = 400) -> str | None:
    """Return the extracted PDF text while preserving the historical API."""
    text, _ = _pdf_to_text_and_pages(data, max_pages=max_pages)
    return text


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
        max_pdf_pages: int = 400,
    ) -> None:
        if max_pdf_pages < 1:
            raise ValueError("max_pdf_pages must be positive")
        self.timeout = timeout
        self.opener = opener or default_opener()
        self.max_pdf_pages = max_pdf_pages

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
                body = response.read()
                if media_type == "application/pdf":
                    extracted, total_pages = _pdf_to_text_and_pages(
                        body, max_pages=self.max_pdf_pages
                    )
                    if extracted is None:
                        return SourceResolution(
                            source=None,
                            failure="pdf_unsupported",
                            detail="application/pdf: no text layer or no extractor",
                        )
                    text = extracted
                    window = EvidenceWindow.from_text(
                        text,
                        original_bytes=len(body),
                        original_characters=None,
                        truncation=(
                            "truncated"
                            if total_pages is not None
                            and total_pages > self.max_pdf_pages
                            else "complete"
                        ),
                        extraction_method=(
                            f"pypdf-text-layer/v1:max_pages={self.max_pdf_pages}"
                        ),
                    )
                else:
                    raw = body.decode("utf-8", errors="replace")
                    text = (
                        html_to_text(raw)
                        if media_type in {"text/html", "application/xhtml+xml"}
                        else raw
                    )
                    window = EvidenceWindow.from_text(
                        text,
                        original_bytes=len(body),
                        original_characters=len(raw),
                        truncation="complete",
                        extraction_method=(
                            "html.parser-visible-text/v1"
                            if media_type in {"text/html", "application/xhtml+xml"}
                            else "http-text:utf-8-errors-replace/v1"
                        ),
                    )
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
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=_now(),
                status=status,
                media_type=media_type,
                evidence_window=window,
            )
        )


class SnapshotStore:
    """JSON source archive keyed by URI hash and verified when reopened.

    Successful reads freeze the source bytes. Failed reads freeze the observed
    failure taxonomy as evidence too; otherwise a live paywall silently turns
    into a generic missing-snapshot error during replay.
    """

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
            "schema": "groundnut-source-snapshot/v2",
            "source_id": source.reference.source_id,
            "uri": source.reference.uri,
            "fetched_at": source.fetched_at,
            "status": source.status,
            "media_type": source.media_type,
            "sha256": sha256_text(source.text),
            "text": source.text,
            "evidence_window": source.evidence_window.to_dict(),
        }
        path.write_text(json.dumps(payload, sort_keys=True))
        return path

    def archive_failure(
        self, reference: SourceReference, resolution: SourceResolution
    ) -> Path:
        if resolution.ok or resolution.failure is None:
            raise ValueError("failure snapshot requires a failed resolution")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(reference.uri)
        payload = {
            "schema": "groundnut-source-failure-snapshot/v1",
            "source_id": reference.source_id,
            "uri": reference.uri,
            "observed_at": _now(),
            "failure": resolution.failure,
            "detail": resolution.detail,
        }
        path.write_text(json.dumps(payload, sort_keys=True))
        return path

    def load(self, reference: SourceReference) -> SourceResolution:
        path = self.path_for(reference.uri)
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return SourceResolution(
                source=None,
                failure="source_changed",
                detail=f"snapshot_unreadable:{type(exc).__name__}",
            )
        schema = value.get("schema")
        if (
            value.get("uri") != reference.uri
            or value.get("source_id") != reference.source_id
        ):
            return SourceResolution(
                source=None, failure="source_changed", detail="snapshot_identity_mismatch"
            )
        if schema == "groundnut-source-failure-snapshot/v1":
            failure = value.get("failure")
            detail = value.get("detail")
            if failure not in FAILURE_STATES or (
                detail is not None and not isinstance(detail, str)
            ):
                return SourceResolution(
                    source=None,
                    failure="source_changed",
                    detail="snapshot_failure_invalid",
                )
            return SourceResolution(source=None, failure=failure, detail=detail)
        if schema not in {
            "groundnut-source-snapshot/v1",
            "groundnut-source-snapshot/v2",
        }:
            return SourceResolution(
                source=None, failure="source_changed", detail="snapshot_schema_unknown"
            )
        text = value.get("text")
        if not isinstance(text, str) or sha256_text(text) != value.get("sha256"):
            return SourceResolution(
                source=None, failure="source_changed", detail="snapshot_hash_mismatch"
            )
        try:
            window = (
                EvidenceWindow.from_mapping(value.get("evidence_window", {}), text=text)
                if schema == "groundnut-source-snapshot/v2"
                else EvidenceWindow.from_text(
                    text,
                    truncation="unknown",
                    extraction_method="legacy-snapshot/v1",
                )
            )
        except (TypeError, ValueError):
            return SourceResolution(
                source=None,
                failure="source_changed",
                detail="snapshot_evidence_window_invalid",
            )
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=str(value["fetched_at"]),
                status=value.get("status"),
                media_type=value.get("media_type"),
                evidence_window=window,
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
        if self.strategy not in {"snapshot", "live_archived", "live_failed", "live_failed_archived", "snapshot_missing", "snapshot_invalid"}:
            raise ValueError(f"unknown source acquisition strategy: {self.strategy}")

    def to_dict(self) -> dict:
        source = self.resolution.source
        return {
            "schema": "groundnut-source-acquisition/v2",
            "mode": self.mode,
            "strategy": self.strategy,
            "snapshot_sha256": self.snapshot_sha256,
            "live_attempted": self.live_attempted,
            "result": {
                "ok": self.resolution.ok,
                "source_id": self.reference.source_id,
                "uri": self.reference.uri,
                "source_sha256": source.record.sha256 if source else None,
                "evidence_window": source.evidence_window.to_dict() if source else None,
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
                strategy=(
                    "snapshot"
                    if resolution.failure != "source_changed"
                    else "snapshot_invalid"
                ),
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
            archived = None
            strategy = "live_failed"
            if not exists:
                archived = self.snapshots.archive_failure(reference, resolution)
                strategy = "live_failed_archived"
            return SourceAcquisition(
                reference=reference,
                resolution=resolution,
                mode=self.mode,
                strategy=strategy,
                snapshot_sha256=(
                    _file_sha256(self.snapshots.path_for(reference.uri))
                    if exists
                    else _file_sha256(archived)
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


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return _required_int(value)


def _required_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("evidence-window lengths must be integers")
    return value

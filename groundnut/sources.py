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


class HttpResolver:
    """Small standard-library HTTP adapter; no provider credentials involved."""

    def __init__(
        self,
        *,
        timeout: int = 20,
        opener: Callable = urllib.request.urlopen,
    ) -> None:
        self.timeout = timeout
        self.opener = opener

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

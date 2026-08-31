"""Source acquisition and snapshot adapters.

Extraction begins with normalized source text, but provenance starts one stage
earlier. Resolvers make acquisition explicit and preserve honest failure states
instead of turning paywalls, unreachable pages, or unsupported PDFs into an
empty source. Snapshots pin what the engine actually saw.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from html.parser import HTMLParser
import http.client
import ipaddress
import io
import json
import hashlib
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.parse
import urllib.request
import zlib

from .provenance import SourceRecord, sha256_text


_SPARSE_HTML_MAX_CHARACTERS = 1024
_SPARSE_HTML_MIN_ORIGINAL_BYTES = 4096
_HOLLOW_HTML_MAX_CHARACTERS = 4096
_HOLLOW_PATTERNS = (
    re.compile(r"\b(?:verify|confirm) (?:that )?you are (?:a )?human\b", re.I),
    re.compile(r"\b(?:captcha|access denied|forbidden|request blocked)\b", re.I),
    re.compile(r"\b(?:enable|requires?) javascript\b", re.I),
    re.compile(r"\bjavascript (?:is required|must be enabled)\b", re.I),
    re.compile(r"\bjust a moment\b.*\b(?:cloudflare|security|browser)\b", re.I | re.S),
    re.compile(r"\bchecking (?:your )?browser\b", re.I),
    re.compile(r"\b(?:too many requests|rate limit(?:ed| exceeded)?)\b", re.I),
    re.compile(r"\b(?:subscribe|sign in|log in) to (?:continue|read|view|access)\b", re.I),
    re.compile(r"\b(?:accept|manage) (?:all )?cookies\b.*\b(?:continue|consent|preferences?)\b", re.I | re.S),
)


def _is_hollow_html(text: str, extraction_method: str) -> bool:
    if not extraction_method.startswith("html.parser-visible-text/"):
        return False
    searchable = text.strip()
    return bool(
        searchable
        and len(searchable) <= _HOLLOW_HTML_MAX_CHARACTERS
        and any(pattern.search(searchable) for pattern in _HOLLOW_PATTERNS)
    )


def _honest_truncation(
    text: str,
    *,
    truncation: str,
    extraction_method: str,
    original_bytes: int | None,
) -> str:
    """Refuse to describe an unusable searchable window as complete."""

    if truncation != "complete":
        return truncation
    if not text.strip():
        return "empty"
    if _is_hollow_html(text, extraction_method):
        return "hollow"
    if (
        extraction_method.startswith("html.parser-visible-text/")
        and len(text) < _SPARSE_HTML_MAX_CHARACTERS
        and original_bytes is not None
        and original_bytes >= _SPARSE_HTML_MIN_ORIGINAL_BYTES
    ):
        return "sparse"
    return truncation


FAILURE_STATES = {
    "source_paywalled",
    "source_unreachable",
    "source_changed",
    "source_policy_blocked",
    "source_too_large",
    "pdf_unsupported",
    "source_media_unsupported",
}

DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_EXTRACTED_CHARACTERS = 8 * 1024 * 1024
DEFAULT_PDF_TIMEOUT_SECONDS = 20
DEFAULT_PDF_CPU_SECONDS = 10
DEFAULT_PDF_MEMORY_BYTES = 512 * 1024 * 1024


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

    TRUNCATION_STATES = {
        "complete",
        "truncated",
        "unknown",
        "empty",
        "sparse",
        "hollow",
    }

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
        honest_truncation = _honest_truncation(
            text,
            truncation=truncation,
            extraction_method=extraction_method,
            original_bytes=original_bytes,
        )
        return cls(
            original_bytes=original_bytes,
            original_characters=original_characters,
            captured_bytes=len(text.encode()),
            captured_characters=len(text),
            truncation=honest_truncation,
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
        recorded_window = cls(
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
            truncation=recorded_window.truncation,
            extraction_method=recorded_window.extraction_method,
            original_bytes=recorded_window.original_bytes,
            original_characters=recorded_window.original_characters,
        )
        if recorded_window != expected and not (
            recorded_window.truncation == "complete"
            and expected.truncation in {"empty", "sparse", "hollow"}
            and replace(expected, truncation="complete") == recorded_window
        ):
            raise ValueError("evidence window does not match captured text")
        if value.get("sha256") != recorded_window.sha256:
            raise ValueError("evidence-window sha256 does not match its content")
        return expected


@dataclass(frozen=True)
class ResolvedSource:
    reference: SourceReference
    text: str
    fetched_at: str
    status: int | None = None
    media_type: str | None = None
    evidence_window: EvidenceWindow | None = None
    final_uri: str | None = None

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
        if self.final_uri is None:
            object.__setattr__(self, "final_uri", self.reference.uri)

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
    data: bytes,
    *,
    max_pages: int = 400,
    max_characters: int = DEFAULT_MAX_EXTRACTED_CHARACTERS,
) -> tuple[str | None, int | None, bool]:
    """Text layer of a PDF via pypdf, page-joined; None when unavailable.

    Scanned PDFs with no text layer return None rather than an empty source,
    so the claim is reported as pdf_unsupported instead of not_found.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - depends on the host environment
        return None, None, False
    try:
        reader = PdfReader(io.BytesIO(data))
        total_pages = len(reader.pages)
        pages = []
        captured = 0
        character_truncated = False
        for page in reader.pages[:max_pages]:
            text = (page.extract_text() or "").strip()
            separator = 2 if pages else 0
            remaining = max_characters - captured - separator
            if remaining <= 0:
                character_truncated = True
                break
            if len(text) > remaining:
                pages.append(text[:remaining])
                captured += separator + remaining
                character_truncated = True
                break
            pages.append(text)
            captured += separator + len(text)
    except Exception:  # pypdf raises a wide family on malformed files
        return None, None, False
    text = "\n\n".join(pages)
    return (text if text.strip() else None), total_pages, character_truncated


def pdf_to_text(data: bytes, *, max_pages: int = 400) -> str | None:
    """Return the extracted PDF text while preserving the historical API."""
    text, _, _ = _pdf_to_text_and_pages(data, max_pages=max_pages)
    return text


def _isolated_pdf_to_text_and_pages(
    data: bytes,
    *,
    max_pages: int,
    max_characters: int,
    timeout_seconds: int,
    cpu_seconds: int,
    memory_bytes: int,
) -> tuple[str | None, int | None, bool, str | None]:
    package_root = Path(__file__).resolve().parent.parent
    max_output_bytes = max(4096, max_characters * 6 + 4096)
    with tempfile.TemporaryDirectory(prefix="groundnut-pdf-") as directory:
        output = Path(directory) / "result.json"
        command = [
            sys.executable,
            "-m",
            "groundnut.pdf_worker",
            "--out",
            str(output),
            "--max-input-bytes",
            str(len(data)),
            "--max-pages",
            str(max_pages),
            "--max-characters",
            str(max_characters),
            "--cpu-seconds",
            str(cpu_seconds),
            "--memory-bytes",
            str(memory_bytes),
            "--max-output-bytes",
            str(max_output_bytes),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=directory,
                env={"PYTHONHASHSEED": "0", "PYTHONPATH": str(package_root)},
            )
            deadline = time.monotonic() + timeout_seconds
            pending_input: bytes | None = data
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.communicate()
                    return None, None, False, "pdf_worker_timeout"
                try:
                    process.communicate(
                        input=pending_input, timeout=min(0.1, remaining)
                    )
                    break
                except subprocess.TimeoutExpired:
                    # communicate() retains the buffered input after a timeout.
                    pending_input = None
                    resident = _resident_memory_bytes(process.pid)
                    if resident is None:
                        process.kill()
                        process.communicate()
                        return None, None, False, "pdf_worker_memory_unobservable"
                    if resident > memory_bytes:
                        process.kill()
                        process.communicate()
                        return None, None, False, "pdf_worker_memory_limit"
        except OSError:
            return None, None, False, "pdf_worker_failed"
        if process.returncode != 0 or not output.is_file():
            return None, None, False, "pdf_worker_failed"
        if output.stat().st_size > max_output_bytes:
            return None, None, False, "pdf_worker_output_exceeds_limit"
        try:
            payload = json.loads(output.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None, None, False, "pdf_worker_output_invalid"
        if payload.get("schema") != "groundnut-pdf-worker-result/v1":
            return None, None, False, "pdf_worker_output_invalid"
        if payload.get("status") != "ok":
            return None, None, False, str(payload.get("detail") or "pdf_unsupported")
        text = payload.get("text")
        total_pages = payload.get("total_pages")
        truncated = payload.get("character_truncated")
        if (
            not isinstance(text, str)
            or len(text) > max_characters
            or not isinstance(total_pages, int)
            or total_pages < 0
            or not isinstance(truncated, bool)
        ):
            return None, None, False, "pdf_worker_output_invalid"
        return text or None, total_pages, truncated, None


def _resident_memory_bytes(pid: int) -> int | None:
    """Return a worker's resident set size without trusting the worker itself."""
    status = Path(f"/proc/{pid}/status")
    if status.is_file():
        try:
            for line in status.read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
        except (OSError, UnicodeError, ValueError, IndexError):
            return None
    try:
        observed = subprocess.run(
            ["/bin/ps", "-o", "rss=", "-p", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
            check=False,
        )
        if observed.returncode == 0 and observed.stdout.strip():
            return int(observed.stdout.strip()) * 1024
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


class _SourcePolicyBlocked(ValueError):
    pass


class _SourceTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class _ValidatedHTTPURI:
    uri: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]
    request_target: str


def _system_addresses(hostname: str, port: int) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            row[4][0]
            for row in socket.getaddrinfo(
                hostname, port, type=socket.SOCK_STREAM
            )
        )
    )


def _validate_public_http_uri(
    uri: str, address_resolver: Callable[[str, int], tuple[str, ...]]
) -> _ValidatedHTTPURI:
    if not isinstance(uri, str) or any(
        ord(character) <= 0x20
        or ord(character) >= 0x7F
        or character == "\\"
        for character in uri
    ):
        raise _SourcePolicyBlocked("invalid_uri")
    try:
        parsed = urllib.parse.urlsplit(uri)
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except (TypeError, ValueError) as exc:
        raise _SourcePolicyBlocked("invalid_uri") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise _SourcePolicyBlocked("scheme_not_allowed")
    if not parsed.hostname:
        raise _SourcePolicyBlocked("hostname_required")
    if "%" in parsed.hostname or "\\" in parsed.hostname:
        raise _SourcePolicyBlocked("invalid_hostname")
    if parsed.username is not None or parsed.password is not None:
        raise _SourcePolicyBlocked("embedded_credentials_not_allowed")
    addresses = address_resolver(parsed.hostname, port)
    if not addresses:
        raise OSError("hostname resolved to no addresses")
    canonical_addresses = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value.split("%", 1)[0])
        except ValueError as exc:
            raise _SourcePolicyBlocked("resolver_returned_invalid_address") from exc
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            raise _SourcePolicyBlocked(f"non_public_address:{address.compressed}")
        canonical_addresses.append(address.compressed)
    path = parsed.path or "/"
    request_target = f"{path}?{parsed.query}" if parsed.query else path
    return _ValidatedHTTPURI(
        uri=uri,
        scheme=parsed.scheme.casefold(),
        hostname=parsed.hostname,
        port=port,
        addresses=tuple(canonical_addresses),
        request_target=request_target,
    )


def _offline_validation_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Supply deterministic addresses for syntax-only replay validation.

    Literal addresses validate as themselves so private-address snapshots still
    fail closed. Hostnames use a fixed public documentation address; replay must
    never perform DNS or make a network request.
    """

    try:
        return (ipaddress.ip_address(hostname).compressed,)
    except ValueError:
        return ("93.184.216.34",)


def _sanitize_final_http_uri(uri: str) -> str:
    """Return a non-secret final-response identity for persistence.

    Query data and fragments are omitted because redirect query values are not
    needed by replay consumers and can contain credentials or tokens. Scheme,
    host, explicit port, and path remain sufficient for wrong-page detection.
    """

    validated = _validate_public_http_uri(uri, _offline_validation_addresses)
    parsed = urllib.parse.urlsplit(uri)
    hostname = parsed.hostname or ""  # validation above requires it
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")
        if (
            len(hostname) > 253
            or any(
                not 1 <= len(label) <= 63
                or not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label
                )
                for label in labels
            )
        ):
            raise _SourcePolicyBlocked("invalid_hostname")
    host = f"[{hostname.lower()}]" if ":" in hostname else hostname.lower()
    explicit_port = parsed.port
    netloc = f"{host}:{explicit_port}" if explicit_port is not None else host
    return urllib.parse.urlunsplit(
        (validated.scheme, netloc, parsed.path or "/", "", "")
    )


def _snapshot_contract_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _default_tls_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:  # pragma: no cover - depends on the host environment
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


class _PinnedResponse:
    def __init__(
        self,
        response: http.client.HTTPResponse,
        connection: http.client.HTTPConnection,
        uri: str,
    ) -> None:
        self._response = response
        self._connection = connection
        self._uri = uri
        self.status = response.status
        self.headers = response.headers

    def read(self, size: int = -1) -> bytes:
        return self._response.read(size)

    def geturl(self) -> str:
        return self._uri

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()

    def __enter__(self) -> "_PinnedResponse":
        return self

    def __exit__(self, *args) -> bool:
        self.close()
        return False


class _PinnedHTTPTransport:
    """HTTP(S) GET transport pinned to preflighted IP addresses."""

    REDIRECTS = {301, 302, 303, 307, 308}
    SAFE_HEADERS = {"accept", "accept-encoding", "user-agent"}

    def __init__(
        self,
        validator: Callable[[str], _ValidatedHTTPURI],
        *,
        tls_context: ssl.SSLContext | None = None,
        max_redirects: int = 10,
    ) -> None:
        self.validator = validator
        self.tls_context = tls_context or _default_tls_context()
        self.max_redirects = max_redirects

    def __call__(self, request, *, timeout):
        current_uri = request.full_url
        headers = {
            name: value
            for name, value in request.header_items()
            if name.casefold() in self.SAFE_HEADERS
        }
        for redirect_count in range(self.max_redirects + 1):
            target = self.validator(current_uri)
            response = self._open(target, headers, timeout)
            location = response.headers.get("Location")
            if response.status not in self.REDIRECTS or not location:
                return response
            response.close()
            if redirect_count == self.max_redirects:
                raise urllib.error.URLError("redirect_limit")
            current_uri = urllib.parse.urljoin(current_uri, location)
        raise urllib.error.URLError("redirect_limit")  # pragma: no cover

    def _open(
        self,
        target: _ValidatedHTTPURI,
        headers: Mapping[str, str],
        timeout: int,
    ) -> _PinnedResponse:
        failures = []
        for address in target.addresses:
            connection = self._connection(target, address, timeout)
            try:
                connection.connect()
                peer = ipaddress.ip_address(connection.sock.getpeername()[0])
                if peer != ipaddress.ip_address(address):
                    raise _SourcePolicyBlocked("connected_peer_mismatch")
                connection.request("GET", target.request_target, headers=dict(headers))
                response = connection.getresponse()
                return _PinnedResponse(response, connection, target.uri)
            except _SourcePolicyBlocked:
                connection.close()
                raise
            except (OSError, http.client.HTTPException) as exc:
                failures.append(exc)
                connection.close()
        if failures:
            raise failures[-1]
        raise OSError("no validated addresses available")

    def _connection(
        self, target: _ValidatedHTTPURI, address: str, timeout: int
    ) -> http.client.HTTPConnection:
        if target.scheme == "https":
            connection = http.client.HTTPSConnection(
                target.hostname,
                target.port,
                timeout=timeout,
                context=self.tls_context,
            )
        else:
            connection = http.client.HTTPConnection(
                target.hostname, target.port, timeout=timeout
            )

        def create_pinned_connection(
            ignored_address,
            connection_timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
            source_address=None,
            *,
            all_errors=False,
        ):
            return socket.create_connection(
                (address, target.port),
                connection_timeout,
                source_address,
                all_errors=all_errors,
            )

        connection._create_connection = create_pinned_connection
        return connection


def _default_public_uri_validator(uri: str) -> _ValidatedHTTPURI:
    return _validate_public_http_uri(uri, _system_addresses)


def default_opener(
    validator: Callable[[str], _ValidatedHTTPURI] | None = None,
) -> Callable:
    """Return the redirect-aware transport pinned to validated addresses."""
    if validator is None:
        validator = _default_public_uri_validator
    return _PinnedHTTPTransport(validator)


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    value = headers.get(name)
    return str(value) if value is not None else None


def _read_limited(response: Any, limit: int) -> bytes:
    declared = _header(response, "Content-Length")
    if declared is not None:
        try:
            declared_bytes = int(declared)
        except ValueError as exc:
            raise _SourcePolicyBlocked("invalid_content_length") from exc
        if declared_bytes < 0:
            raise _SourcePolicyBlocked("invalid_content_length")
        if declared_bytes > limit:
            raise _SourceTooLarge("response_content_length_exceeds_limit")
    body = response.read(limit + 1)
    if len(body) > limit:
        raise _SourceTooLarge("response_body_exceeds_limit")
    return body


def _bounded_zlib_decode(data: bytes, *, limit: int, wbits: int) -> bytes:
    decoder = zlib.decompressobj(wbits)
    decoded = decoder.decompress(data, limit + 1)
    if len(decoded) > limit or decoder.unconsumed_tail:
        raise _SourceTooLarge("decompressed_body_exceeds_limit")
    remaining = limit + 1 - len(decoded)
    tail = decoder.flush(remaining) if remaining > 0 else b""
    decoded += tail
    if len(decoded) > limit:
        raise _SourceTooLarge("decompressed_body_exceeds_limit")
    if not decoder.eof or decoder.unused_data:
        raise _SourcePolicyBlocked("invalid_compressed_body")
    return decoded


def _decode_content(data: bytes, encoding: str | None, *, limit: int) -> bytes:
    normalized = (encoding or "identity").strip().casefold()
    if normalized in {"", "identity"}:
        if len(data) > limit:
            raise _SourceTooLarge("decoded_body_exceeds_limit")
        return data
    try:
        if normalized in {"gzip", "x-gzip"}:
            return _bounded_zlib_decode(data, limit=limit, wbits=16 + zlib.MAX_WBITS)
        if normalized == "deflate":
            try:
                return _bounded_zlib_decode(data, limit=limit, wbits=zlib.MAX_WBITS)
            except (_SourcePolicyBlocked, zlib.error):
                return _bounded_zlib_decode(data, limit=limit, wbits=-zlib.MAX_WBITS)
    except zlib.error as exc:
        raise _SourcePolicyBlocked("invalid_compressed_body") from exc
    raise _SourcePolicyBlocked("content_encoding_not_allowed")


class HttpResolver:
    """Fail-closed HTTP adapter for untrusted evidence URIs and response bytes.

    The default transport validates every destination and binds each connection
    to one of the public addresses returned by that validation, while retaining
    the original hostname for the HTTP Host header and TLS verification.
    Injected HTTP/DNS transports are privileged test or specialist-host seams
    and require an explicit opt-in because their connection behavior cannot be
    constrained by the default transport.
    """

    def __init__(
        self,
        *,
        timeout: int = 20,
        opener: Callable | None = None,
        address_resolver: Callable[[str, int], tuple[str, ...]] | None = None,
        allow_injected_transport: bool = False,
        max_pdf_pages: int = 400,
        pdf_timeout_seconds: int = DEFAULT_PDF_TIMEOUT_SECONDS,
        pdf_cpu_seconds: int = DEFAULT_PDF_CPU_SECONDS,
        pdf_memory_bytes: int = DEFAULT_PDF_MEMORY_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_decompressed_bytes: int = DEFAULT_MAX_DECOMPRESSED_BYTES,
        max_extracted_characters: int = DEFAULT_MAX_EXTRACTED_CHARACTERS,
    ) -> None:
        limits = (
            max_pdf_pages,
            pdf_timeout_seconds,
            pdf_cpu_seconds,
            pdf_memory_bytes,
            max_response_bytes,
            max_decompressed_bytes,
            max_extracted_characters,
        )
        if any(value < 1 for value in limits):
            raise ValueError("resolver limits must be positive")
        if (opener is not None or address_resolver is not None) and not (
            allow_injected_transport
        ):
            raise ValueError(
                "injected HTTP or DNS transport is privileged; "
                "set allow_injected_transport=True explicitly"
            )
        self.timeout = timeout
        self.address_resolver = address_resolver or _system_addresses
        self._validate_uri = lambda uri: _validate_public_http_uri(
            uri, self.address_resolver
        )
        self.opener = opener or default_opener(self._validate_uri)
        self.max_pdf_pages = max_pdf_pages
        self.pdf_timeout_seconds = pdf_timeout_seconds
        self.pdf_cpu_seconds = pdf_cpu_seconds
        self.pdf_memory_bytes = pdf_memory_bytes
        self.max_response_bytes = max_response_bytes
        self.max_decompressed_bytes = max_decompressed_bytes
        self.max_extracted_characters = max_extracted_characters

    def resolve(self, reference: SourceReference) -> SourceResolution:
        try:
            self._validate_uri(reference.uri)
            request = urllib.request.Request(
                reference.uri,
                headers={
                    "User-Agent": "groundnut/0.1 source-verification",
                    "Accept": "text/html,text/plain,application/json,application/xml,application/pdf;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            with self.opener(request, timeout=self.timeout) as response:
                final_uri = (
                    response.geturl()
                    if hasattr(response, "geturl")
                    else reference.uri
                )
                self._validate_uri(final_uri)
                persisted_final_uri = _sanitize_final_http_uri(final_uri)
                status = getattr(response, "status", None)
                if isinstance(status, int) and status >= 300:
                    failure = (
                        "source_paywalled"
                        if status in {401, 402, 403, 429}
                        else "source_unreachable"
                    )
                    return SourceResolution(
                        source=None, failure=failure, detail=f"http_{status}"
                    )
                media_type = response.headers.get_content_type()
                encoded_body = _read_limited(response, self.max_response_bytes)
                body = _decode_content(
                    encoded_body,
                    _header(response, "Content-Encoding"),
                    limit=self.max_decompressed_bytes,
                )
                if media_type == "application/pdf":
                    (
                        extracted,
                        total_pages,
                        character_truncated,
                        pdf_failure,
                    ) = _isolated_pdf_to_text_and_pages(
                        body,
                        max_pages=self.max_pdf_pages,
                        max_characters=self.max_extracted_characters,
                        timeout_seconds=self.pdf_timeout_seconds,
                        cpu_seconds=self.pdf_cpu_seconds,
                        memory_bytes=self.pdf_memory_bytes,
                    )
                    if extracted is None:
                        return SourceResolution(
                            source=None,
                            failure="pdf_unsupported",
                            detail=pdf_failure or "application/pdf: no text layer",
                        )
                    text = extracted
                    window = EvidenceWindow.from_text(
                        text,
                        original_bytes=len(body),
                        original_characters=None,
                        truncation=(
                            "truncated"
                            if character_truncated
                            or (
                                total_pages is not None
                                and total_pages > self.max_pdf_pages
                            )
                            else "complete"
                        ),
                        extraction_method=(
                            "pypdf-text-layer/v2:"
                            f"max_pages={self.max_pdf_pages}:"
                            f"max_characters={self.max_extracted_characters}"
                        ),
                    )
                else:
                    if not (
                        media_type.startswith("text/")
                        or media_type
                        in {
                            "application/json",
                            "application/xml",
                            "application/xhtml+xml",
                        }
                    ):
                        return SourceResolution(
                            source=None,
                            failure="source_media_unsupported",
                            detail=media_type,
                        )
                    raw = body.decode("utf-8", errors="replace")
                    text = (
                        html_to_text(raw)
                        if media_type in {"text/html", "application/xhtml+xml"}
                        else raw
                    )
                    character_truncated = len(text) > self.max_extracted_characters
                    if character_truncated:
                        text = text[: self.max_extracted_characters]
                    window = EvidenceWindow.from_text(
                        text,
                        original_bytes=len(body),
                        original_characters=len(raw),
                        truncation="truncated" if character_truncated else "complete",
                        extraction_method=(
                            "html.parser-visible-text/v1"
                            if media_type in {"text/html", "application/xhtml+xml"}
                            else "http-text:utf-8-errors-replace/v1"
                        ),
                    )
        except _SourcePolicyBlocked as exc:
            return SourceResolution(
                source=None,
                failure="source_policy_blocked",
                detail=str(exc),
            )
        except _SourceTooLarge as exc:
            return SourceResolution(
                source=None,
                failure="source_too_large",
                detail=str(exc),
            )
        except http.client.InvalidURL:
            return SourceResolution(
                source=None,
                failure="source_policy_blocked",
                detail="invalid_uri",
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
                final_uri=persisted_final_uri,
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
            "schema": "groundnut-source-snapshot/v3",
            "source_id": source.reference.source_id,
            "uri": source.reference.uri,
            "final_uri": _sanitize_final_http_uri(source.final_uri),
            "fetched_at": source.fetched_at,
            "status": source.status,
            "media_type": source.media_type,
            "sha256": sha256_text(source.text),
            "text": source.text,
            "evidence_window": source.evidence_window.to_dict(),
        }
        payload["snapshot_sha256"] = _snapshot_contract_sha256(payload)
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
        # URI is the canonical snapshot identity: the store is keyed by it and
        # report extraction derives its own stable source id from it. A host's
        # source_id is attribution metadata and may differ across read phases.
        # Ignoring that label here migrates existing snapshots on read.
        if value.get("uri") != reference.uri:
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
            "groundnut-source-snapshot/v3",
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
                if schema in {
                    "groundnut-source-snapshot/v2",
                    "groundnut-source-snapshot/v3",
                }
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
        final_uri = reference.uri
        if schema == "groundnut-source-snapshot/v3":
            recorded_final_uri = value.get("final_uri")
            if not isinstance(recorded_final_uri, str):
                return SourceResolution(
                    source=None,
                    failure="source_changed",
                    detail="snapshot_final_uri_invalid:required_string",
                )
            try:
                sanitized_final_uri = _sanitize_final_http_uri(recorded_final_uri)
            except _SourcePolicyBlocked as exc:
                return SourceResolution(
                    source=None,
                    failure="source_changed",
                    detail=f"snapshot_final_uri_invalid:{exc}",
                )
            if recorded_final_uri != sanitized_final_uri:
                return SourceResolution(
                    source=None,
                    failure="source_changed",
                    detail="snapshot_final_uri_invalid:not_sanitized",
                )
            contract = dict(value)
            recorded_contract_sha256 = contract.pop("snapshot_sha256", None)
            if recorded_contract_sha256 != _snapshot_contract_sha256(contract):
                return SourceResolution(
                    source=None,
                    failure="source_changed",
                    detail="snapshot_contract_hash_mismatch",
                )
            final_uri = recorded_final_uri
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=text,
                fetched_at=str(value["fetched_at"]),
                status=value.get("status"),
                media_type=value.get("media_type"),
                evidence_window=window,
                final_uri=final_uri,
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
                "final_uri": source.final_uri if source else None,
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

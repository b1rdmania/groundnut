"""Declared read-time source capture over Groundnut's snapshot contract."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from .sources import (
    HttpResolver,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceAcquisition,
    SourceReference,
    SourceResolution,
    SourceResolver,
)


CAPTURE_REQUEST_SCHEMA = "groundnut-read-capture-request/v1"
CAPTURE_RECEIPT_SCHEMA = "groundnut-read-capture/v1"
ALLOWED_MEDIA_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/pdf",
}
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:^|[_-])(token|secret|password|passwd|key|sig|signature|credential|session|auth)(?:$|[_-])",
    re.IGNORECASE,
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CaptureDeclaration:
    """Non-secret connector policy approved before a source is read."""

    connector: str
    media_types: tuple[str, ...]
    intent: str = "evidence_verification"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.connector):
            raise ValueError("connector must be a lowercase stable identifier")
        if self.intent != "evidence_verification":
            raise ValueError("unsupported capture intent")
        if not self.media_types or len(set(self.media_types)) != len(self.media_types):
            raise ValueError("media_types must be non-empty and unique")
        unknown = set(self.media_types) - ALLOWED_MEDIA_TYPES
        if unknown:
            raise ValueError(f"unsupported declared media types: {sorted(unknown)}")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-capture-declaration/v1",
            "connector": self.connector,
            "intent": self.intent,
            "media_types": sorted(self.media_types),
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CaptureDeclaration":
        if not isinstance(value, Mapping):
            raise ValueError("capture declaration must be an object")
        if set(value) != {"connector", "intent", "media_types"}:
            raise ValueError("capture declaration has unknown or missing fields")
        media_types = value["media_types"]
        if not isinstance(media_types, list) or not all(
            isinstance(item, str) for item in media_types
        ):
            raise ValueError("capture declaration media_types must be strings")
        return cls(
            connector=str(value["connector"]),
            intent=str(value["intent"]),
            media_types=tuple(media_types),
        )


def validate_public_reference(reference: SourceReference) -> None:
    """Reject credentials in canonical source identity instead of redacting it."""

    parsed = urlsplit(reference.uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("read-time HTTP capture requires an http(s) URI")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URI must not contain credentials")
    sensitive = [key for key, _ in parse_qsl(parsed.query) if _SENSITIVE_QUERY_KEY.search(key)]
    if sensitive:
        raise ValueError("source URI contains a credential-shaped query parameter")


class _DeclaredResolver:
    def __init__(self, resolver: SourceResolver, declaration: CaptureDeclaration) -> None:
        self.resolver = resolver
        self.declaration = declaration

    def resolve(self, reference: SourceReference) -> SourceResolution:
        try:
            resolution = self.resolver.resolve(reference)
        except Exception:
            # Connector exceptions are an untrusted boundary. Their messages
            # commonly contain request URLs, headers, cookies or retry dumps.
            return SourceResolution(
                source=None,
                failure="source_unreachable",
                detail="connector_exception",
            )
        if not resolution.ok:
            return SourceResolution(
                source=None,
                failure=resolution.failure,
                detail=_safe_failure_detail(resolution.detail),
            )
        assert resolution.source is not None
        if resolution.source.media_type not in self.declaration.media_types:
            return SourceResolution(
                source=None,
                failure="source_media_unsupported",
                detail="declared_media_type_mismatch",
            )
        return resolution


def _safe_failure_detail(detail: str | None) -> str | None:
    """Retain only bounded connector diagnostics with no user-controlled text."""

    if detail is None:
        return None
    if re.fullmatch(r"http_[1-5][0-9]{2}", detail):
        return detail
    if detail == "application/pdf: no text layer or no extractor":
        return detail
    return "connector_detail_redacted"


class ReadTimeCaptureProducer:
    """Archive the first approved connector read; later reads replay it."""

    def __init__(
        self,
        snapshots: SnapshotStore,
        resolver: SourceResolver,
        declaration: CaptureDeclaration,
    ) -> None:
        self.snapshots = snapshots
        self.declaration = declaration
        self.resolver = SnapshotFirstResolver(
            snapshots,
            _DeclaredResolver(resolver, declaration),
            mode="snapshot_preferred",
        )

    def capture(self, reference: SourceReference) -> dict[str, Any]:
        validate_public_reference(reference)
        acquisition = self.resolver.acquire(reference)
        return capture_receipt(acquisition, self.declaration)


def capture_receipt(
    acquisition: SourceAcquisition, declaration: CaptureDeclaration
) -> dict[str, Any]:
    payload = {
        "schema": CAPTURE_RECEIPT_SCHEMA,
        "declaration": declaration.to_dict(),
        "acquisition": acquisition.to_dict(),
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def execute_request(
    request: Mapping[str, Any], *, base_directory: str | Path, allow_live: bool
) -> dict[str, Any]:
    if request.get("schema") != CAPTURE_REQUEST_SCHEMA:
        raise ValueError("unsupported read-capture request schema")
    if not allow_live:
        raise ValueError("read-time capture requires --allow-live")
    if set(request) != {"schema", "snapshot_directory", "declaration", "sources"}:
        raise ValueError("read-capture request has unknown or missing fields")
    base = Path(base_directory).resolve()
    snapshot_directory = Path(str(request["snapshot_directory"])).expanduser()
    if not snapshot_directory.is_absolute():
        snapshot_directory = base / snapshot_directory
    declaration = CaptureDeclaration.from_mapping(request["declaration"])
    sources = request["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a non-empty array")
    producer = ReadTimeCaptureProducer(
        SnapshotStore(snapshot_directory), HttpResolver(), declaration
    )
    receipts = []
    for row in sources:
        if not isinstance(row, Mapping) or set(row) != {"source_id", "uri"}:
            raise ValueError("each source must contain exactly source_id and uri")
        receipts.append(
            producer.capture(SourceReference(str(row["source_id"]), str(row["uri"])))
        )
    payload = {
        "schema": "groundnut-read-capture-batch/v1",
        "declaration_sha256": declaration.sha256,
        "receipts": receipts,
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture declared source reads")
    parser.add_argument("request", help="groundnut-read-capture-request/v1 JSON")
    parser.add_argument("--out", required=True, help="batch receipt path")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args(argv)
    request_path = Path(args.request).resolve()
    try:
        request = json.loads(request_path.read_text())
        result = execute_request(
            request, base_directory=request_path.parent, allow_live=args.allow_live
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "captured", "receipts": len(result["receipts"]), "sha256": result["sha256"]}, sort_keys=True))
    return 0

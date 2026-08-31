"""Declared read-time source capture over Groundnut's snapshot contract."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .sources import (
    HttpResolver,
    ResolvedSource,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceAcquisition,
    SourceReference,
    SourceResolution,
    SourceResolver,
    _sanitize_final_http_uri,
)


CAPTURE_REQUEST_SCHEMA = "groundnut-read-capture-request/v2"
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
    retained_query_parameters: tuple[str, ...] = ()
    retained_query_parameters_by_host: Mapping[str, tuple[str, ...]] | None = None
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
        if len(set(self.retained_query_parameters)) != len(
            self.retained_query_parameters
        ):
            raise ValueError("retained_query_parameters must be unique")
        for name in self.retained_query_parameters:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", name):
                raise ValueError("retained query parameter names must be stable identifiers")
            if _SENSITIVE_QUERY_KEY.search(name):
                raise ValueError("credential-shaped query parameters cannot be retained")
        if self.retained_query_parameters_by_host is not None:
            if self.retained_query_parameters:
                raise ValueError("v3 host query policy cannot be combined with v2 retention")
            normalised: dict[str, tuple[str, ...]] = {}
            for host, names in self.retained_query_parameters_by_host.items():
                if not isinstance(host, str) or host != host.lower() or not re.fullmatch(
                    r"[a-z0-9.-]+", host
                ):
                    raise ValueError("retained-query hosts must be exact lower-case names")
                if "*" in host:
                    raise ValueError("retained-query hosts do not support wildcards")
                values = tuple(names)
                if len(values) != len(set(values)):
                    raise ValueError("host retained query parameters must be unique")
                for name in values:
                    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", name):
                        raise ValueError("retained query parameter names must be stable identifiers")
                    if _SENSITIVE_QUERY_KEY.search(name):
                        raise ValueError("credential-shaped query parameters cannot be retained")
                normalised[host] = tuple(sorted(values))
            object.__setattr__(
                self,
                "retained_query_parameters_by_host",
                MappingProxyType(dict(sorted(normalised.items()))),
            )

    @property
    def schema(self) -> str:
        return (
            "groundnut-capture-declaration/v3"
            if self.retained_query_parameters_by_host is not None
            else "groundnut-capture-declaration/v2"
        )

    def canonical_payload(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "connector": self.connector,
            "intent": self.intent,
            "media_types": sorted(self.media_types),
        }
        if self.schema.endswith("/v2"):
            payload["retained_query_parameters"] = sorted(
                self.retained_query_parameters
            )
        else:
            payload["retained_query_parameters_by_host"] = {
                host: list(names)
                for host, names in self.retained_query_parameters_by_host.items()
            }
        return payload

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CaptureDeclaration":
        if not isinstance(value, Mapping):
            raise ValueError("capture declaration must be an object")
        fields = set(value) - {"schema", "sha256"}
        common = {"connector", "intent", "media_types"}
        v2 = fields == common | {"retained_query_parameters"}
        v3 = fields == common | {"retained_query_parameters_by_host"}
        if not (v2 or v3):
            raise ValueError("capture declaration has unknown or missing fields")
        media_types = value["media_types"]
        if not isinstance(media_types, list) or not all(
            isinstance(item, str) for item in media_types
        ):
            raise ValueError("capture declaration media_types must be strings")
        retained: tuple[str, ...] = ()
        retained_by_host: Mapping[str, tuple[str, ...]] | None = None
        if v2:
            raw_retained = value["retained_query_parameters"]
            if not isinstance(raw_retained, list) or not all(
                isinstance(item, str) for item in raw_retained
            ):
                raise ValueError("retained_query_parameters must be strings")
            retained = tuple(raw_retained)
        else:
            raw_hosts = value["retained_query_parameters_by_host"]
            if not isinstance(raw_hosts, Mapping) or not all(
                isinstance(host, str)
                and isinstance(names, list)
                and all(isinstance(name, str) for name in names)
                for host, names in raw_hosts.items()
            ):
                raise ValueError("retained_query_parameters_by_host must map hosts to strings")
            retained_by_host = {
                host: tuple(names) for host, names in raw_hosts.items()
            }
        declaration = cls(
            connector=str(value["connector"]),
            intent=str(value["intent"]),
            media_types=tuple(media_types),
            retained_query_parameters=retained,
            retained_query_parameters_by_host=retained_by_host,
        )
        schema = value.get("schema")
        if schema is not None and schema != declaration.schema:
            raise ValueError("capture declaration schema does not match its fields")
        if "sha256" in value and value["sha256"] != declaration.sha256:
            raise ValueError("capture declaration sha256 does not match its content")
        return declaration


def canonical_reference(
    reference: SourceReference, declaration: CaptureDeclaration
) -> SourceReference:
    """Reject credentials in canonical source identity instead of redacting it."""

    parsed = urlsplit(reference.uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("read-time HTTP capture requires an http(s) URI")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URI must not contain credentials")
    if declaration.retained_query_parameters_by_host is None:
        retain = set(declaration.retained_query_parameters)
        netloc = parsed.netloc
    else:
        host = (parsed.hostname or "").lower()
        retain = set(declaration.retained_query_parameters_by_host.get(host, ()))
        netloc = parsed.netloc.lower()
    retained = [(key, value) for key, value in parse_qsl(parsed.query) if key in retain]
    canonical_uri = urlunsplit(
        (parsed.scheme, netloc, parsed.path, urlencode(sorted(retained)), "")
    )
    return SourceReference(reference.source_id, canonical_uri)


def query_policy_application(
    reference: SourceReference, declaration: CaptureDeclaration
) -> dict[str, Any]:
    """Describe v3 query-policy application without serializing query values."""

    parsed = urlsplit(reference.uri)
    host = (parsed.hostname or "").lower()
    allowed = set(
        declaration.retained_query_parameters_by_host.get(host, ())
        if declaration.retained_query_parameters_by_host is not None
        else declaration.retained_query_parameters
    )
    present = [key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    sensitive = [key for key in present if _SENSITIVE_QUERY_KEY.search(key)]
    public = [key for key in present if not _SENSITIVE_QUERY_KEY.search(key)]
    return {
        "schema": "groundnut-query-policy-application/v1",
        "host": host,
        "keys_present": sorted(set(public)),
        "keys_retained": sorted({key for key in public if key in allowed}),
        "non_sensitive_keys_dropped": sorted(
            {key for key in public if key not in allowed}
        ),
        "credential_shaped_keys_dropped_count": len(sensitive),
    }


SNAPSHOT_RESOLUTION_FAILURES = {
    "snapshot_missing",
    "source_changed",
    "http_status",
    "empty_text",
    "incomplete_evidence_window",
    "hollow_capture",
}


@dataclass(frozen=True)
class SnapshotResolution:
    raw_reference: SourceReference
    canonical_reference: SourceReference
    snapshot_key: str
    snapshot_path: str
    source: ResolvedSource | None = None
    failure: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if (self.source is None) == (self.failure is None):
            raise ValueError("snapshot resolution must contain source or failure")
        if self.failure is not None and self.failure not in SNAPSHOT_RESOLUTION_FAILURES:
            raise ValueError(f"unknown snapshot resolution failure: {self.failure}")

    @property
    def ok(self) -> bool:
        return self.source is not None

    @property
    def evidence_window(self):
        return self.source.evidence_window if self.source else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-snapshot-resolution/v1",
            "ok": self.ok,
            "raw_identity": {
                "source_id": self.raw_reference.source_id,
                "uri": self.raw_reference.uri,
            },
            "canonical_identity": {
                "source_id": self.canonical_reference.source_id,
                "uri": self.canonical_reference.uri,
            },
            "snapshot_key": self.snapshot_key,
            "snapshot_path": self.snapshot_path,
            "source": (
                {
                    "text": self.source.text,
                    "status": self.source.status,
                    "media_type": self.source.media_type,
                    "final_uri": self.source.final_uri,
                    "evidence_window": self.source.evidence_window.to_dict(),
                }
                if self.source
                else None
            ),
            "failure": self.failure,
            "detail": self.detail,
        }


def resolve_snapshot(
    reference: SourceReference,
    declaration: CaptureDeclaration,
    store: SnapshotStore,
) -> SnapshotResolution:
    """Resolve exactly one canonical snapshot identity without live fallback."""

    canonical = canonical_reference(reference, declaration)
    path = store.path_for(canonical.uri)
    common = {
        "raw_reference": reference,
        "canonical_reference": canonical,
        "snapshot_key": store.key(canonical.uri),
        "snapshot_path": str(path),
    }
    if not store.contains(canonical):
        return SnapshotResolution(**common, failure="snapshot_missing")
    replay = store.load(canonical)
    if not replay.ok:
        if replay.failure == "source_changed":
            return SnapshotResolution(
                **common, failure="source_changed", detail=replay.detail
            )
        return SnapshotResolution(
            **common, failure="http_status", detail=replay.detail or replay.failure
        )
    source = replay.source
    assert source is not None
    if source.status is not None and not 200 <= source.status < 300:
        return SnapshotResolution(
            **common, failure="http_status", detail=f"http_{source.status}"
        )
    if not source.text.strip() or source.evidence_window.truncation == "empty":
        return SnapshotResolution(**common, failure="empty_text")
    if source.evidence_window.truncation == "hollow":
        return SnapshotResolution(**common, failure="hollow_capture")
    if source.evidence_window.truncation != "complete":
        return SnapshotResolution(
            **common,
            failure="incomplete_evidence_window",
            detail=source.evidence_window.truncation,
        )
    return SnapshotResolution(**common, source=source)


def validate_public_reference(reference: SourceReference) -> None:
    """Compatibility validator using the default-deny query policy."""

    canonical_reference(reference, CaptureDeclaration("public_web", ("text/html",)))


class _DeclaredResolver:
    def __init__(
        self,
        resolver: SourceResolver,
        declaration: CaptureDeclaration,
        fetch_reference: SourceReference,
    ) -> None:
        self.resolver = resolver
        self.declaration = declaration
        self.fetch_reference = fetch_reference

    def resolve(self, reference: SourceReference) -> SourceResolution:
        try:
            resolution = self.resolver.resolve(self.fetch_reference)
        except Exception as error:
            # Connector exceptions are an untrusted boundary. Their messages
            # commonly contain request URLs, headers, cookies or retry dumps.
            return SourceResolution(
                source=None,
                failure="source_unreachable",
                detail=_bounded_detail("connector_exception", str(error)),
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
                detail=_bounded_detail(
                    "declared_media_type_mismatch",
                    resolution.source.media_type or "unknown",
                ),
            )
        source = resolution.source
        try:
            final_uri = _sanitize_final_http_uri(source.final_uri)
        except ValueError as error:
            return SourceResolution(
                source=None,
                failure="source_policy_blocked",
                detail=_bounded_detail("invalid_final_response_uri", str(error)),
            )
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text=source.text,
                fetched_at=source.fetched_at,
                status=source.status,
                media_type=source.media_type,
                evidence_window=source.evidence_window,
                final_uri=final_uri,
            )
        )


def _safe_failure_detail(detail: str | None) -> str | None:
    """Retain only bounded connector diagnostics with no user-controlled text."""

    if detail is None:
        return None
    if re.fullmatch(r"http_[1-5][0-9]{2}", detail):
        return detail
    if detail == "application/pdf: no text layer or no extractor":
        return detail
    return _bounded_detail("connector_detail_redacted", detail)


def _bounded_detail(classification: str, raw_detail: str) -> str:
    digest = hashlib.sha256(
        b"groundnut-capture-detail/v1\0" + raw_detail.encode(errors="replace")
    ).hexdigest()[:16]
    return f"{classification};detail_ref=sha256:{digest}"


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
        self.live_resolver = resolver

    def capture(self, reference: SourceReference) -> dict[str, Any]:
        canonical = canonical_reference(reference, self.declaration)
        resolver = SnapshotFirstResolver(
            self.snapshots,
            _DeclaredResolver(
                self.live_resolver, self.declaration, fetch_reference=reference
            ),
            mode="snapshot_preferred",
        )
        acquisition = resolver.acquire(canonical)
        return capture_receipt(acquisition, self.declaration, reference=reference)


def capture_receipt(
    acquisition: SourceAcquisition,
    declaration: CaptureDeclaration,
    *,
    reference: SourceReference | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": CAPTURE_RECEIPT_SCHEMA,
        "declaration": declaration.to_dict(),
        "acquisition": acquisition.to_dict(),
    }
    if declaration.schema.endswith("/v3"):
        if reference is None:
            raise ValueError("v3 capture receipt requires the raw source reference")
        payload["query_policy_application"] = query_policy_application(
            reference, declaration
        )
    return {**payload, "sha256": _canonical_sha256(payload)}


def validate_capture_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate declaration and receipt hashes, returning a detached mapping."""

    if not isinstance(value, Mapping) or value.get("schema") != CAPTURE_RECEIPT_SCHEMA:
        raise ValueError("unsupported capture receipt schema")
    if "sha256" not in value:
        raise ValueError("capture receipt sha256 is required")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if value["sha256"] != _canonical_sha256(payload):
        raise ValueError("capture receipt sha256 does not match its content")
    declaration = CaptureDeclaration.from_mapping(value.get("declaration", {}))
    if declaration.schema.endswith("/v3"):
        _validate_query_policy_application(
            value.get("query_policy_application"), value.get("acquisition", {})
        )
    elif "query_policy_application" in value:
        raise ValueError("v2 capture receipt must not contain query_policy_application")
    return dict(value)


def _validate_query_policy_application(value: Any, acquisition: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("v3 capture receipt requires query_policy_application")
    expected_fields = {
        "schema",
        "host",
        "keys_present",
        "keys_retained",
        "non_sensitive_keys_dropped",
        "credential_shaped_keys_dropped_count",
    }
    if set(value) != expected_fields:
        raise ValueError("query_policy_application has unknown or missing fields")
    if value["schema"] != "groundnut-query-policy-application/v1":
        raise ValueError("unsupported query_policy_application schema")
    host = value["host"]
    if not isinstance(host, str) or not host:
        raise ValueError("query_policy_application host must be a non-empty string")
    if host != _capture_receipt_result_host(acquisition):
        raise ValueError("query_policy_application host does not match acquisition")
    present = _query_policy_string_array(value["keys_present"], "keys_present")
    retained = _query_policy_string_array(value["keys_retained"], "keys_retained")
    dropped = _query_policy_string_array(
        value["non_sensitive_keys_dropped"], "non_sensitive_keys_dropped"
    )
    retained_set = set(retained)
    dropped_set = set(dropped)
    if not retained_set.issubset(present) or not dropped_set.issubset(present):
        raise ValueError("query_policy_application key arrays are inconsistent")
    if retained_set & dropped_set:
        raise ValueError("query_policy_application retained and dropped keys overlap")
    count = value["credential_shaped_keys_dropped_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            "query_policy_application credential_shaped_keys_dropped_count "
            "must be a non-negative integer"
        )


def _capture_receipt_result_host(acquisition: Any) -> str:
    if not isinstance(acquisition, Mapping):
        raise ValueError("capture receipt acquisition must be an object")
    result = acquisition.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("capture receipt acquisition result must be an object")
    uri = result.get("uri")
    if not isinstance(uri, str):
        raise ValueError("capture receipt acquisition result uri must be a string")
    host = urlsplit(uri).hostname
    if not host:
        raise ValueError("capture receipt acquisition result uri must include a host")
    return host


def _query_policy_string_array(value: Any, field: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"query_policy_application {field} must be a string array")
    if len(value) != len(set(value)):
        raise ValueError(f"query_policy_application {field} must contain unique strings")
    return set(value)


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
    parser.add_argument("request", help="groundnut-read-capture-request/v2 JSON")
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

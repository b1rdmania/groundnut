"""Compare live and replay evidence, then prove deterministic replay bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


RECEIPT_SCHEMA = "groundnut-live-replay-equivalence/v1"
PROJECTION_SCHEMA = "groundnut-live-replay-evidence-projection/v1"

COMPARED_FIELDS = (
    "/execution/run/artifact",
    "/execution/run/acquisitions/*/snapshot_sha256",
    "/execution/run/acquisitions/*/result/{ok,source_id,uri,source_sha256,evidence_window,failure,detail}",
    "/execution/run/evidence",
    "/execution/run/arena",
    "/execution/manifest/{engine,domain,sources,policies,components}",
    "/execution/manifest/artifacts/*[kind!=canonical_run]",
)

EXCLUDED_FIELDS = (
    {
        "path": "/request_sha256",
        "reason": "live and replay requests declare different acquisition modes",
    },
    {
        "path": "/execution/run/acquisitions/*/{mode,strategy,live_attempted}",
        "reason": "declared acquisition metadata differs by design",
    },
    {
        "path": "/execution/run/sha256",
        "reason": "derived from the complete run including acquisition metadata",
    },
    {
        "path": "/execution/manifest/artifacts/*[kind=canonical_run]",
        "reason": "canonical-run digest binds the deliberately different complete run",
    },
    {
        "path": "/execution/manifest/sha256",
        "reason": "derived from the manifest including the complete-run digest",
    },
    {
        "path": "/execution/sha256",
        "reason": "derived from the complete run and manifest",
    },
)


def compare_documents(
    live_document: bytes,
    replay_document: bytes,
    replay_second_document: bytes,
) -> dict[str, Any]:
    """Return a privacy-safe comparison receipt for three canonical documents."""

    live = _load_document(live_document, "live")
    replay = _load_document(replay_document, "replay")
    replay_second = _load_document(replay_second_document, "replay_second")
    live_execution = _execution(live, "live")
    replay_execution = _execution(replay, "replay")
    replay_second_execution = _execution(replay_second, "replay_second")
    live_projection = _projection(live_execution, "live")
    replay_projection = _projection(replay_execution, "replay")
    replay_second_projection = _projection(
        replay_second_execution, "replay_second"
    )
    live_differences = _differences(live_projection, replay_projection)
    replay_differences = _differences(
        replay_projection, replay_second_projection
    )
    replay_assertions = {
        "first": _replay_assertions(replay_execution),
        "second": _replay_assertions(replay_second_execution),
    }
    live_assertions = _live_assertions(live_execution)
    replay_bytes_identical = replay_document == replay_second_document
    equivalent = (
        not live_differences
        and not replay_differences
        and replay_bytes_identical
        and live_assertions["live_mode_declared"]
        and all(row["valid"] for row in replay_assertions.values())
    )
    payload = {
        "schema": RECEIPT_SCHEMA,
        "status": "equivalent" if equivalent else "different",
        "compared_fields": list(COMPARED_FIELDS),
        "excluded_fields": list(EXCLUDED_FIELDS),
        "expected_nondeterminism": [
            "request hash",
            "acquisition mode",
            "acquisition strategy",
            "live-attempt state",
            "hashes derived from the complete acquisition-bearing run",
        ],
        "documents": {
            "live": _document_identity(live_document, live_execution, live_projection),
            "replay": _document_identity(
                replay_document, replay_execution, replay_projection
            ),
            "replay_second": _document_identity(
                replay_second_document,
                replay_second_execution,
                replay_second_projection,
            ),
        },
        "live_acquisition": live_assertions,
        "replay_acquisition": replay_assertions,
        "replay_byte_identical": replay_bytes_identical,
        "differences": {
            "live_vs_replay": live_differences,
            "replay_vs_replay_second": replay_differences,
        },
        "disclosure": (
            "Equivalent means the compared evidence projection is identical and "
            "two replay documents are byte-identical. It does not claim that two "
            "independent live fetches are deterministic. Difference rows contain "
            "hashes only and do not disclose private claim or source text."
        ),
    }
    payload["sha256"] = _payload_sha256(payload)
    validate_receipt(payload)
    return payload


def validate_receipt(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fail closed when a comparison receipt drops fields or contradicts itself."""

    if value.get("schema") != RECEIPT_SCHEMA:
        raise ValueError("unsupported live/replay equivalence receipt schema")
    if value.get("compared_fields") != list(COMPARED_FIELDS):
        raise ValueError("equivalence receipt compared-field set is incomplete")
    if value.get("excluded_fields") != list(EXCLUDED_FIELDS):
        raise ValueError("equivalence receipt excluded-field set is incomplete")
    _validate_hash(value, "equivalence receipt")
    differences = _mapping(value, "differences", "receipt")
    live_differences = _difference_rows(
        differences.get("live_vs_replay"), "live_vs_replay"
    )
    replay_differences = _difference_rows(
        differences.get("replay_vs_replay_second"),
        "replay_vs_replay_second",
    )
    replay = _mapping(value, "replay_acquisition", "receipt")
    first = _mapping(replay, "first", "receipt replay_acquisition")
    second = _mapping(replay, "second", "receipt replay_acquisition")
    live = _mapping(value, "live_acquisition", "receipt")
    equivalent = (
        not live_differences
        and not replay_differences
        and value.get("replay_byte_identical") is True
        and live.get("live_mode_declared") is True
        and first.get("valid") is True
        and second.get("valid") is True
    )
    expected = "equivalent" if equivalent else "different"
    if value.get("status") != expected:
        raise ValueError("equivalence receipt status contradicts its checks")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", required=True, type=Path)
    parser.add_argument("--replay", required=True, type=Path)
    parser.add_argument("--replay-second", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_documents(
            args.live.read_bytes(),
            args.replay.read_bytes(),
            args.replay_second.read_bytes(),
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        print(f"INVALID: {error}")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "replay_byte_identical": result["replay_byte_identical"],
                "live_vs_replay_differences": len(
                    result["differences"]["live_vs_replay"]
                ),
                "sha256": result["sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "equivalent" else 1


def _load_document(document: bytes, label: str) -> Mapping[str, Any]:
    value = json.loads(
        document.decode("utf-8"),
        parse_constant=lambda constant: _reject_constant(constant),
    )
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} document must be an object")
    return value


def _execution(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if value.get("schema") == "groundnut-canonical-response/v1":
        value = _mapping(value, "execution", label)
    if value.get("schema") != "groundnut-canonical-execution/v1":
        raise ValueError(f"{label} has unsupported canonical execution schema")
    run = _mapping(value, "run", label)
    manifest = _mapping(value, "manifest", label)
    if run.get("schema") != "groundnut-canonical-run/v1":
        raise ValueError(f"{label} has unsupported canonical run schema")
    if manifest.get("schema") != "groundnut-run-manifest/v2":
        raise ValueError(f"{label} has unsupported run manifest schema")
    _validate_hash(run, f"{label} run")
    _validate_hash(manifest, f"{label} manifest")
    _validate_hash(value, f"{label} execution")
    _validate_manifest_binding(run, manifest, label)
    return value


def _projection(execution: Mapping[str, Any], label: str) -> dict[str, Any]:
    run = _mapping(execution, "run", label)
    manifest = _mapping(execution, "manifest", label)
    artifact = _mapping(run, "artifact", label)
    evidence = _mapping(run, "evidence", label)
    engine = _mapping(manifest, "engine", label)
    domain = _mapping(manifest, "domain", label)
    sources = list(_sequence(manifest, "sources", label))
    policies = list(_sequence(manifest, "policies", label))
    components = list(_sequence(manifest, "components", label))
    manifest_artifacts = list(_sequence(manifest, "artifacts", label))
    acquisitions = _sequence(run, "acquisitions", label)
    projected_acquisitions = []
    identities = set()
    for index, acquisition in enumerate(acquisitions):
        row = _as_mapping(acquisition, f"{label} acquisition {index}")
        if row.get("schema") != "groundnut-source-acquisition/v2":
            raise ValueError(f"{label} acquisition {index} is not v2")
        result = _mapping(row, "result", f"{label} acquisition {index}")
        source_id = _required_text(result.get("source_id"), "source_id")
        uri = _required_text(result.get("uri"), "uri")
        identity = (source_id, uri)
        if identity in identities:
            raise ValueError(f"{label} has duplicate acquisition identity")
        identities.add(identity)
        if not isinstance(result.get("ok"), bool):
            raise ValueError(f"{label} acquisition result ok must be boolean")
        snapshot_sha256 = row.get("snapshot_sha256")
        if snapshot_sha256 is not None:
            _require_sha256(snapshot_sha256, "snapshot_sha256")
        source_sha256 = result.get("source_sha256")
        evidence_window = result.get("evidence_window")
        if result["ok"]:
            _require_sha256(source_sha256, "source_sha256")
            window = _as_mapping(
                evidence_window, f"{label} acquisition evidence_window"
            )
            if window.get("schema") != "groundnut-evidence-window/v1":
                raise ValueError(f"{label} has unsupported evidence-window schema")
            _validate_hash(window, f"{label} evidence window")
            if result.get("failure") is not None:
                raise ValueError(f"{label} successful acquisition carries failure")
        elif source_sha256 is not None or evidence_window is not None:
            raise ValueError(f"{label} failed acquisition carries source evidence")
        elif not isinstance(result.get("failure"), str):
            raise ValueError(f"{label} failed acquisition has no failure state")
        projected_acquisitions.append(
            {
                "snapshot_sha256": snapshot_sha256,
                "result": {
                    key: result.get(key)
                    for key in (
                        "ok",
                        "source_id",
                        "uri",
                        "source_sha256",
                        "evidence_window",
                        "failure",
                        "detail",
                    )
                },
            }
        )
    projected_acquisitions.sort(
        key=lambda row: (
            row["result"]["source_id"],
            row["result"]["uri"],
        )
    )
    projection = {
        "schema": PROJECTION_SCHEMA,
        "artifact": artifact,
        "acquisitions": projected_acquisitions,
        "evidence": evidence,
        "arena": run.get("arena"),
        "manifest": {
            "engine": engine,
            "domain": domain,
            "sources": sources,
            "policies": policies,
            "components": components,
            "artifacts": [
                row
                for row in manifest_artifacts
                if not isinstance(row, Mapping)
                or row.get("kind") != "canonical_run"
            ],
        },
    }
    _canonical_bytes(projection)
    return projection


def _live_assertions(execution: Mapping[str, Any]) -> dict[str, Any]:
    acquisitions = _sequence(
        _mapping(execution, "run", "live"), "acquisitions", "live"
    )
    modes = [
        _as_mapping(row, "live acquisition").get("mode") for row in acquisitions
    ]
    attempts = sum(
        _as_mapping(row, "live acquisition").get("live_attempted") is True
        for row in acquisitions
    )
    return {
        "acquisitions": len(acquisitions),
        "live_mode_declared": all(mode != "replay_only" for mode in modes),
        "live_attempted": attempts,
    }


def _replay_assertions(execution: Mapping[str, Any]) -> dict[str, Any]:
    acquisitions = _sequence(
        _mapping(execution, "run", "replay"), "acquisitions", "replay"
    )
    rows = [_as_mapping(row, "replay acquisition") for row in acquisitions]
    replay_only = all(row.get("mode") == "replay_only" for row in rows)
    no_live_attempts = all(row.get("live_attempted") is False for row in rows)
    snapshot_strategy = all(row.get("strategy") == "snapshot" for row in rows)
    return {
        "acquisitions": len(rows),
        "replay_only": replay_only,
        "no_live_attempts": no_live_attempts,
        "snapshot_strategy": snapshot_strategy,
        "valid": replay_only and no_live_attempts and snapshot_strategy,
    }


def _document_identity(
    document: bytes,
    execution: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    run = _mapping(execution, "run", "document")
    return {
        "document_sha256": hashlib.sha256(document).hexdigest(),
        "execution_sha256": execution.get("sha256"),
        "run_sha256": run.get("sha256"),
        "evidence_projection_sha256": hashlib.sha256(
            _canonical_bytes(projection)
        ).hexdigest(),
    }


def _differences(left: Any, right: Any, path: str = "") -> list[dict[str, str]]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        rows = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}/{_pointer_token(str(key))}"
            if key not in left or key not in right:
                rows.append(
                    _difference(
                        child,
                        left.get(key, _MISSING),
                        right.get(key, _MISSING),
                    )
                )
            else:
                rows.extend(_differences(left[key], right[key], child))
        return rows
    if isinstance(left, list) and isinstance(right, list):
        rows = []
        for index in range(max(len(left), len(right))):
            child = f"{path}/{index}"
            if index >= len(left) or index >= len(right):
                rows.append(
                    _difference(
                        child,
                        left[index] if index < len(left) else _MISSING,
                        right[index] if index < len(right) else _MISSING,
                    )
                )
            else:
                rows.extend(_differences(left[index], right[index], child))
        return rows
    return [] if left == right else [_difference(path or "/", left, right)]


def _difference(path: str, left: Any, right: Any) -> dict[str, str]:
    return {
        "path": path,
        "left_sha256": _value_sha256(left),
        "right_sha256": _value_sha256(right),
    }


def _value_sha256(value: Any) -> str:
    if value is _MISSING:
        value = {"missing": True}
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {key: value for key, value in payload.items() if key != "sha256"}
        )
    ).hexdigest()


def _validate_hash(value: Mapping[str, Any], label: str) -> None:
    declared = value.get("sha256")
    actual = hashlib.sha256(
        _canonical_bytes(
            {key: row for key, row in value.items() if key != "sha256"}
        )
    ).hexdigest()
    if declared != actual:
        raise ValueError(f"{label} sha256 does not match its content")


def _validate_manifest_binding(
    run: Mapping[str, Any], manifest: Mapping[str, Any], label: str
) -> None:
    artifacts = _sequence(manifest, "artifacts", label)
    run_bytes = _canonical_bytes(run)
    run_sha256 = hashlib.sha256(run_bytes).hexdigest()
    matches = [
        row
        for row in artifacts
        if isinstance(row, Mapping)
        and row.get("kind") == "canonical_run"
        and row.get("schema") == run.get("schema")
        and row.get("sha256") == run_sha256
        and row.get("bytes") == len(run_bytes)
    ]
    if len(matches) != 1:
        raise ValueError(f"{label} manifest does not bind the canonical run")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _mapping(value: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    return _as_mapping(value.get(key), f"{label} {key}")


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Mapping[str, Any], key: str, label: str) -> Sequence[Any]:
    rows = value.get(key)
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"{label} {key} must be an array")
    return rows


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _difference_rows(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"receipt {label} differences must be an array")
    for row in value:
        item = _as_mapping(row, f"receipt {label} difference")
        if set(item) != {"path", "left_sha256", "right_sha256"}:
            raise ValueError(f"receipt {label} difference has unknown fields")
        _required_text(item.get("path"), "difference path")
        _require_sha256(item.get("left_sha256"), "difference left_sha256")
        _require_sha256(item.get("right_sha256"), "difference right_sha256")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


_MISSING = object()


if __name__ == "__main__":
    raise SystemExit(main())

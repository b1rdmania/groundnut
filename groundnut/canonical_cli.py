"""Versioned JSON process boundary for the canonical Groundnut engine."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from .arena_emission import ArenaEmissionProfile, DEFAULT_ARENA_EMISSION_PROFILE
from .artifacts import ArtifactProfile, DEFAULT_ARTIFACT_PROFILE
from .authority import AuthorityDeclaration, AuthorityPolicy
from .domain import DomainPack
from .run_manifest import EngineIdentity
from .runner import execute_canonical_check
from .sources import HttpResolver, SnapshotFirstResolver, SnapshotStore
from .support import ExactSupportDetector, SupportPolicy


REQUEST_SCHEMA = "groundnut-canonical-request/v1"
RESPONSE_SCHEMA = "groundnut-canonical-response/v1"
ERROR_SCHEMA = "groundnut-canonical-error/v1"
ENGINE_VERSION = "0.1"
_REPOSITORY = Path(__file__).resolve().parent.parent


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _resolve_path(value: Any, *, base: Path, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty path")
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _load_mapping(value: Any, *, base: Path, label: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        path = _resolve_path(value, base=base, label=label)
        return _require_object(json.loads(path.read_text()), label)
    return _require_object(value, label)


def _artifact_profile(value: Any) -> ArtifactProfile:
    if value is None:
        return DEFAULT_ARTIFACT_PROFILE
    return ArtifactProfile.from_mapping(_require_object(value, "artifact_profile"))


def _arena_profile(value: Any) -> ArenaEmissionProfile | None:
    if value in (None, False):
        return None
    if value is True:
        return DEFAULT_ARENA_EMISSION_PROFILE
    return ArenaEmissionProfile.from_mapping(_require_object(value, "arena_profile"))


def _authority_declarations(value: Any) -> dict[str, AuthorityDeclaration]:
    if value is None:
        return {}
    rows = _require_object(value, "authority_declarations")
    return {
        str(claim_id): AuthorityDeclaration.from_mapping(
            _require_object(row, f"authority_declarations.{claim_id}")
        )
        for claim_id, row in rows.items()
    }


def execute_request(
    request: Mapping[str, Any],
    *,
    base_directory: str | Path,
    allow_live: bool = False,
) -> dict[str, Any]:
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"unsupported canonical request schema: {request.get('schema')!r}")
    base = Path(base_directory).resolve()
    artifact = _resolve_path(request.get("artifact"), base=base, label="artifact")
    snapshots = _resolve_path(
        request.get("snapshot_directory"), base=base, label="snapshot_directory"
    )
    domain = DomainPack.from_mapping(
        _load_mapping(request.get("domain"), base=base, label="domain")
    )
    support_policy = SupportPolicy.from_mapping(
        _load_mapping(
            request.get("support_policy"), base=base, label="support_policy"
        )
    )
    detector = ExactSupportDetector()
    if support_policy.detector != detector.identity:
        raise ValueError("canonical CLI currently admits only the frozen exact baseline")
    authority_policy = AuthorityPolicy.from_mapping(
        _load_mapping(
            request.get("authority_policy"), base=base, label="authority_policy"
        )
    )
    mode = str(request.get("acquisition_mode", "replay_only"))
    if mode != "replay_only" and not allow_live:
        raise ValueError("live acquisition requires the --allow-live process flag")
    resolver = SnapshotFirstResolver(
        SnapshotStore(snapshots),
        HttpResolver() if mode != "replay_only" else None,
        mode=mode,
    )
    execution = execute_canonical_check(
        artifact,
        engine=EngineIdentity.from_repository(
            version=ENGINE_VERSION,
            repository=_REPOSITORY,
        ),
        domain=domain,
        artifact_profile=_artifact_profile(request.get("artifact_profile")),
        resolver=resolver,
        detector=detector,
        support_policy=support_policy,
        authority_policy=authority_policy,
        authority_declarations=_authority_declarations(
            request.get("authority_declarations")
        ),
        arena_profile=_arena_profile(request.get("arena_profile")),
        publication_grade=bool(request.get("publication_grade", False)),
    )
    return {
        "schema": RESPONSE_SCHEMA,
        "request_sha256": _canonical_sha256(request),
        "execution": execution.to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--request",
        help="request JSON; omit to read one JSON object from stdin",
    )
    parser.add_argument("--out", help="response JSON; omit to write stdout")
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="permit explicit snapshot_preferred or refresh acquisition",
    )
    return parser


def _write(value: Mapping[str, Any], path: str | None, *, stream) -> None:
    encoded = json.dumps(value, sort_keys=True, indent=2) + "\n"
    if path:
        Path(path).write_text(encoded)
    else:
        stream.write(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.request:
            request_path = Path(args.request).expanduser().resolve()
            request = _require_object(json.loads(request_path.read_text()), "request")
            base = request_path.parent
        else:
            request = _require_object(json.load(sys.stdin), "request")
            base = Path.cwd()
        response = execute_request(
            request,
            base_directory=base,
            allow_live=args.allow_live,
        )
        _write(response, args.out, stream=sys.stdout)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        _write(
            {
                "schema": ERROR_SCHEMA,
                "error": type(error).__name__,
                "message": str(error),
            },
            None,
            stream=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

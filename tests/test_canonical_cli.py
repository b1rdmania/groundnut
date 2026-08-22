import json
from pathlib import Path
import subprocess
import sys

import pytest

from groundnut.canonical_cli import ERROR_SCHEMA, RESPONSE_SCHEMA, execute_request
from groundnut.provenance import sha256_text
from groundnut.sources import ResolvedSource, SnapshotStore, SourceReference


ROOT = Path(__file__).parent.parent


def _request(tmp_path):
    artifact = tmp_path / "claims.json"
    artifact.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "revenue",
                        "claim_text": "Revenue was 4.2 million.",
                        "source_url": "https://example.test/filing",
                    }
                ]
            }
        )
    )
    store = SnapshotStore(tmp_path / "snapshots")
    store.archive(
        ResolvedSource(
            reference=SourceReference(
                source_id=f"url:{sha256_text('https://example.test/filing')[:16]}",
                uri="https://example.test/filing",
            ),
            text="Revenue was 4.2 million.",
            fetched_at="2026-08-17T00:00:00Z",
        )
    )
    return {
        "schema": "groundnut-canonical-request/v1",
        "artifact": str(artifact),
        "snapshot_directory": str(tmp_path / "snapshots"),
        "domain": str(ROOT / "domains" / "ma_dd.json"),
        "support_policy": str(
            ROOT / "policies" / "exact-support-baseline-v1.json"
        ),
        "authority_policy": {
            "schema": "groundnut-authority-policy/v1",
            "key": "canonical_authority",
            "version": "1",
            "frozen_at": "2026-08-17T00:00:00Z",
        },
        "arena_profile": False,
    }


def test_execute_request_replays_snapshot_and_returns_versioned_execution(tmp_path):
    response = execute_request(_request(tmp_path), base_directory=tmp_path)
    assert response["schema"] == RESPONSE_SCHEMA
    assert len(response["request_sha256"]) == 64
    execution = response["execution"]
    assert execution["run"]["acquisitions"][0]["strategy"] == "snapshot"
    assert execution["run"]["evidence"]["summary"]["support_status_counts"] == {
        "supported": 1
    }
    assert execution["manifest"]["domain"]["key"] == "ma_dd"


def test_execute_request_accepts_separate_arena_artifact(tmp_path):
    request = _request(tmp_path)
    original = tmp_path / "original.md"
    original.write_text(
        "Therefore the company is likely to sustain this revenue level for the next year."
    )
    request["arena_profile"] = True
    request["arena_artifact"] = str(original)
    response = execute_request(request, base_directory=tmp_path)
    assert response["execution"]["run"]["arena"]["tasks"][0]["trigger"] == "inferential"


def test_execute_request_requires_separate_live_process_permission(tmp_path):
    request = _request(tmp_path)
    request["acquisition_mode"] = "refresh"
    with pytest.raises(ValueError, match="--allow-live"):
        execute_request(request, base_directory=tmp_path)


def test_module_cli_reads_stdin_and_writes_one_json_response(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "groundnut.canonical_cli"],
        cwd=ROOT,
        input=json.dumps(_request(tmp_path)),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["schema"] == RESPONSE_SCHEMA


def test_module_cli_fails_closed_with_machine_readable_error():
    result = subprocess.run(
        [sys.executable, "-m", "groundnut.canonical_cli"],
        cwd=ROOT,
        input='{"schema":"wrong"}',
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr)["schema"] == ERROR_SCHEMA


def test_canonical_path_refuses_unadmitted_detectors():
    from groundnut.admitted_detectors import (
        admitted_detector_identities,
        build_admitted_detector,
    )
    from groundnut.support import DetectorIdentity, ExactSupportDetector

    assert list(admitted_detector_identities()) == [ExactSupportDetector.identity]
    foreign = DetectorIdentity(
        adapter="groundnut.alignscore",
        model="nli",
        revision="1",
        package="alignscore",
        package_version="0.1",
    )
    with pytest.raises(ValueError, match="not admitted to the canonical path"):
        build_admitted_detector(foreign)

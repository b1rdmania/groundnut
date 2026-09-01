import json
from pathlib import Path
import socket

import pytest

from groundnut.artifacts import DEFAULT_ARTIFACT_PROFILE
from groundnut.authority import AuthorityPolicy
from groundnut import canonical_cli
from groundnut.canonical_cli import execute_request
from groundnut.domain import Category, DomainPack
from groundnut.equivalence import (
    V1_COMPARED_FIELDS,
    _payload_sha256,
    compare_documents,
    main,
    validate_receipt,
)
from groundnut.provenance import sha256_text
from groundnut.run_manifest import EngineIdentity
from groundnut.runner import execute_canonical_check
from groundnut.sources import (
    EvidenceWindow,
    ResolvedSource,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceReference,
    SourceResolution,
)
from groundnut.support import ExactSupportDetector, SupportPolicy


SUPPORT_POLICY = SupportPolicy(
    key="exact",
    version="1",
    frozen_at="2026-08-25T00:00:00Z",
    detector=ExactSupportDetector.identity,
    min_confidence=1.0,
)
AUTHORITY_POLICY = AuthorityPolicy(
    key="authority",
    version="1",
    frozen_at="2026-08-25T00:00:00Z",
)
DOMAIN = DomainPack(
    key="equivalence_fixture",
    version="1",
    name="Equivalence fixture",
    document_noun="fixture",
    extract_context="Extract the fixture claim.",
    classify_context="Classify fixture evidence.",
    categories=(Category("claim", "Claim", 1),),
)
ENGINE = EngineIdentity(
    version="0.1.0a6",
    revision="fixture-revision",
    source_sha256="a" * 64,
    dirty=False,
)
URI = "https://example.test/seabrook/permit"
SOURCE_TEXT = "The coastal permit was issued on 4 March 2026."
ROOT = Path(__file__).parent.parent


class FixtureLiveResolver:
    def __init__(self, text=SOURCE_TEXT):
        self.text = text
        self.calls = 0

    def resolve(self, reference):
        self.calls += 1
        return SourceResolution(source=_source(reference, self.text))


class NetworkDisabledResolver:
    def __init__(self):
        self.calls = 0

    def resolve(self, reference):  # pragma: no cover - any call fails the test
        self.calls += 1
        raise AssertionError("network resolver invoked during replay")


def _source(reference, text):
    return ResolvedSource(
        reference=reference,
        text=text,
        fetched_at="2026-08-25T00:00:00Z",
        status=200,
        media_type="text/plain",
        evidence_window=EvidenceWindow.from_text(
            text,
            original_bytes=len(text.encode()),
            original_characters=len(text),
            truncation="complete",
            extraction_method="equivalence-fixture/v1",
        ),
    )


def _artifact(tmp_path):
    path = tmp_path / "memo.json"
    path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "permit-date",
                        "claim_text": SOURCE_TEXT,
                        "source_url": URI,
                        "source_excerpt": SOURCE_TEXT,
                    }
                ]
            }
        )
    )
    return path


def _execute(artifact, resolver):
    return execute_canonical_check(
        artifact,
        engine=ENGINE,
        domain=DOMAIN,
        artifact_profile=DEFAULT_ARTIFACT_PROFILE,
        resolver=resolver,
        detector=ExactSupportDetector(),
        support_policy=SUPPORT_POLICY,
        authority_policy=AUTHORITY_POLICY,
    )


def _document(execution, request_sha256):
    return (
        json.dumps(
            {
                "schema": "groundnut-canonical-response/v1",
                "request_sha256": request_sha256,
                "execution": execution.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _rehash(value):
    value.pop("sha256", None)
    value["sha256"] = sha256_text(_canonical_bytes(value).decode())


def _rewrite_acquisitions(document, *, schema, remove_final_uri):
    value = json.loads(document)
    execution = value["execution"]
    run = execution["run"]
    for acquisition in run["acquisitions"]:
        acquisition["schema"] = schema
        if remove_final_uri:
            acquisition["result"].pop("final_uri", None)
    _rehash(run)
    run_bytes = _canonical_bytes(run)
    for artifact in execution["manifest"]["artifacts"]:
        if artifact.get("kind") == "canonical_run":
            artifact["sha256"] = sha256_text(run_bytes.decode())
            artifact["bytes"] = len(run_bytes)
    _rehash(execution["manifest"])
    _rehash(execution)
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _as_historical_v2_acquisitions(document):
    return _rewrite_acquisitions(
        document,
        schema="groundnut-source-acquisition/v2",
        remove_final_uri=True,
    )


def _live_and_replays(tmp_path, *, replay_text=None):
    artifact = _artifact(tmp_path)
    store = SnapshotStore(tmp_path / "snapshots")
    live_resolver = FixtureLiveResolver()
    live = _execute(
        artifact,
        SnapshotFirstResolver(store, live_resolver, mode="snapshot_preferred"),
    )
    if replay_text is not None:
        reference = live.run.acquisitions[0].reference
        store.archive(_source(reference, replay_text))
    disabled = NetworkDisabledResolver()
    replay_resolver = SnapshotFirstResolver(
        store, disabled, mode="replay_only"
    )
    replay = _execute(artifact, replay_resolver)
    replay_second = _execute(artifact, replay_resolver)
    return (
        _document(live, "1" * 64),
        _document(replay, "2" * 64),
        _document(replay_second, "2" * 64),
        live_resolver,
        disabled,
    )


def test_live_replay_equivalence_and_replay_bytes_with_network_disabled(
    tmp_path, monkeypatch
):
    def deny_network(*args, **kwargs):
        raise AssertionError("socket network access is disabled")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    live, replay, replay_second, live_resolver, disabled = _live_and_replays(
        tmp_path
    )

    result = compare_documents(live, replay, replay_second)

    assert result["status"] == "equivalent"
    assert result["replay_byte_identical"] is True
    assert result["differences"] == {
        "live_vs_replay": [],
        "replay_vs_replay_second": [],
    }
    assert result["live_acquisition"]["live_attempted"] == 1
    assert result["replay_acquisition"]["first"]["valid"] is True
    assert result["replay_acquisition"]["second"]["valid"] is True
    assert live_resolver.calls == 1
    assert disabled.calls == 0
    assert len(result["sha256"]) == 64


def test_historical_v2_acquisitions_without_final_uri_remain_readable(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)

    result = compare_documents(
        _as_historical_v2_acquisitions(live),
        _as_historical_v2_acquisitions(replay),
        _as_historical_v2_acquisitions(replay_second),
    )

    assert result["status"] == "equivalent"
    assert result["schema"] == "groundnut-live-replay-equivalence/v2"


def test_v3_successful_acquisition_requires_final_uri(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)
    missing_final_uri = _rewrite_acquisitions(
        live,
        schema="groundnut-source-acquisition/v3",
        remove_final_uri=True,
    )

    with pytest.raises(ValueError, match="v3 acquisition final_uri"):
        compare_documents(missing_final_uri, replay, replay_second)


def test_evidence_drift_is_hash_only_and_never_hidden(tmp_path):
    changed = "The coastal permit date was not available."
    live, replay, replay_second, _, _ = _live_and_replays(
        tmp_path, replay_text=changed
    )

    result = compare_documents(live, replay, replay_second)
    encoded = json.dumps(result, sort_keys=True)

    assert result["status"] == "different"
    assert result["differences"]["live_vs_replay"]
    assert changed not in encoded
    assert SOURCE_TEXT not in encoded
    assert all(
        set(row) == {"path", "left_sha256", "right_sha256"}
        for row in result["differences"]["live_vs_replay"]
    )


def test_semantically_equal_but_nonidentical_replay_bytes_fail(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)

    result = compare_documents(live, replay, replay_second + b"\n")

    assert result["status"] == "different"
    assert result["differences"]["replay_vs_replay_second"] == []
    assert result["replay_byte_identical"] is False


def test_equivalence_cli_writes_machine_receipt(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)
    paths = {}
    for name, document in (
        ("live", live),
        ("replay", replay),
        ("replay-second", replay_second),
    ):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_bytes(document)
    out = tmp_path / "equivalence.json"

    code = main(
        [
            "--live",
            str(paths["live"]),
            "--replay",
            str(paths["replay"]),
            "--replay-second",
            str(paths["replay-second"]),
            "--out",
            str(out),
        ]
    )
    payload = json.loads(out.read_text())

    assert code == 0
    assert payload["schema"] == "groundnut-live-replay-equivalence/v2"
    assert payload["status"] == "equivalent"


def test_comparator_rejects_tampered_canonical_hashes(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)
    tampered = json.loads(replay)
    tampered["execution"]["run"]["evidence"]["summary"]["claims"] = 99
    tampered_bytes = (json.dumps(tampered, sort_keys=True) + "\n").encode()

    with pytest.raises(ValueError, match="run sha256"):
        compare_documents(live, tampered_bytes, replay_second)


def test_receipt_validator_rejects_a_missing_comparison_contract(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)
    result = compare_documents(live, replay, replay_second)
    result["compared_fields"].pop()

    with pytest.raises(ValueError, match="compared-field set"):
        validate_receipt(result)


def test_historical_v1_equivalence_receipt_remains_readable(tmp_path):
    live, replay, replay_second, _, _ = _live_and_replays(tmp_path)
    result = compare_documents(live, replay, replay_second)
    result["schema"] = "groundnut-live-replay-equivalence/v1"
    result["compared_fields"] = list(V1_COMPARED_FIELDS)
    result["sha256"] = _payload_sha256(result)

    assert validate_receipt(result) is result


def test_same_canonical_replay_request_is_byte_identical_without_network(
    tmp_path, monkeypatch
):
    artifact = _artifact(tmp_path)
    snapshots = SnapshotStore(tmp_path / "canonical-snapshots")
    reference_id = f"url:{sha256_text(URI)[:16]}"
    snapshots.archive(_source(SourceReference(reference_id, URI), SOURCE_TEXT))
    request = {
        "schema": "groundnut-canonical-request/v1",
        "artifact": str(artifact),
        "snapshot_directory": str(snapshots.directory),
        "domain": str(ROOT / "domains" / "ma_dd.json"),
        "support_policy": str(
            ROOT / "policies" / "exact-support-baseline-v1.json"
        ),
        "authority_policy": {
            "schema": "groundnut-authority-policy/v1",
            "key": "replay-fixture",
            "version": "1",
            "frozen_at": "2026-08-25T00:00:00Z",
        },
        "acquisition_mode": "replay_only",
        "publication_grade": False,
    }

    def deny_network(*args, **kwargs):
        raise AssertionError("network access attempted during replay")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(canonical_cli, "HttpResolver", deny_network)
    first = execute_request(request, base_directory=tmp_path, allow_live=False)
    second = execute_request(request, base_directory=tmp_path, allow_live=False)
    first_bytes = (json.dumps(first, indent=2, sort_keys=True) + "\n").encode()
    second_bytes = (json.dumps(second, indent=2, sort_keys=True) + "\n").encode()

    assert first["request_sha256"] == second["request_sha256"]
    assert first_bytes == second_bytes

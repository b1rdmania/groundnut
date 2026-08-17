from dataclasses import replace

import pytest

from groundnut.arena import ArenaPolicy
from groundnut.domain import Category, DomainPack
from groundnut.provenance import SourceRecord, sha256_text
from groundnut.run_manifest import (
    ArtifactDigest,
    DomainDigest,
    EngineIdentity,
    PolicyDigest,
    RunManifest,
    RuntimeComponent,
    SourceDigest,
    source_tree_sha256,
)
from groundnut.support import ExactSupportDetector, SupportPolicy


def domain():
    return DomainPack(
        key="test",
        version="1",
        name="Test",
        document_noun="document",
        extract_context="Find relevant text.",
        classify_context="Classify the document.",
        categories=(Category("risk", "Risk", 3),),
    )


def manifest():
    support = SupportPolicy(
        key="support",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=ExactSupportDetector.identity,
        min_confidence=1.0,
    )
    arena = ArenaPolicy(
        key="arena",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        lenses=("premise",),
    )
    source = SourceRecord.from_text("s1", "source text")
    result = {
        "schema": "groundnut-analysis/v1",
        "domain": {"key": "test"},
        "findings": {},
    }
    return RunManifest(
        engine=EngineIdentity(
            version="0.1",
            revision="5bee6ce",
            source_sha256="a" * 64,
            dirty=False,
        ),
        domain=DomainDigest.from_pack(domain()),
        sources=(SourceDigest.from_record(source),),
        policies=(
            PolicyDigest.from_policy("support", support),
            PolicyDigest.from_policy("arena", arena),
        ),
        components=(
            RuntimeComponent.from_config(
                role="analysis_backend",
                name="replay",
                revision="fixture-v1",
                configuration={"temperature": 0, "prompt_sha256": "abc"},
            ),
        ),
        artifacts=(ArtifactDigest.from_value("analysis", result),),
    )


def test_manifest_is_order_stable_and_carries_self_hash():
    first = manifest()
    second = replace(
        first,
        policies=tuple(reversed(first.policies)),
        sources=tuple(reversed(first.sources)),
    )

    assert first.sha256 == second.sha256
    assert first.to_dict()["sha256"] == first.sha256
    assert first.to_dict()["engine"]["revision"] == "5bee6ce"
    assert first.to_dict()["engine"]["source_sha256"] == "a" * 64
    assert first.to_dict()["engine"]["publishable"] is True
    assert first.to_dict()["schema"] == "groundnut-run-manifest/v2"
    assert first.to_dict()["domain"]["playbook_sha256"] == domain().playbook_sha256


def test_artifact_digest_is_canonical_but_semantic_changes_move_hash():
    left = ArtifactDigest.from_value(
        "analysis", {"schema": "x/v1", "a": 1, "b": 2}
    )
    reordered = ArtifactDigest.from_value(
        "analysis", {"b": 2, "schema": "x/v1", "a": 1}
    )
    changed = ArtifactDigest.from_value(
        "analysis", {"schema": "x/v1", "a": 1, "b": 3}
    )

    assert left == reordered
    assert left.sha256 != changed.sha256


def test_source_or_snapshot_change_moves_manifest_hash():
    first = manifest()
    changed_source = SourceDigest(
        source_id="s1",
        sha256=sha256_text("changed source"),
        characters=len("changed source"),
        snapshot_sha256=sha256_text("snapshot bytes"),
    )
    second = replace(first, sources=(changed_source,))

    assert first.sha256 != second.sha256


def test_manifest_rejects_duplicates_and_moving_revisions():
    first = manifest()
    with pytest.raises(ValueError, match="duplicate.*source"):
        replace(first, sources=(first.sources[0], first.sources[0]))
    with pytest.raises(ValueError, match="moving ref"):
        EngineIdentity(
            version="0.1",
            revision="main",
            source_sha256="a" * 64,
            dirty=False,
        )


def test_artifact_requires_schema_and_finite_canonical_json():
    with pytest.raises(ValueError, match="declare a schema"):
        ArtifactDigest.from_value("analysis", {"value": 1})
    with pytest.raises(ValueError, match="JSON compliant"):
        ArtifactDigest.from_value("analysis", {"schema": "x/v1", "value": float("nan")})


def test_source_tree_identity_changes_without_revision_change(tmp_path):
    package = tmp_path / "groundnut"
    package.mkdir()
    source = package / "engine.py"
    source.write_text("RESULT = 1\n")
    clean = EngineIdentity.from_source_tree(
        version="0.1",
        revision="5bee6ce",
        source_root=package,
        dirty=False,
    )

    source.write_text("RESULT = 2\n")
    changed = EngineIdentity.from_source_tree(
        version="0.1",
        revision="5bee6ce",
        source_root=package,
        dirty=True,
    )

    assert clean.revision == changed.revision
    assert clean.source_sha256 != changed.source_sha256
    assert clean.to_dict() != changed.to_dict()
    assert clean.publishable is True
    assert changed.publishable is False
    with pytest.raises(ValueError, match="clean engine build"):
        changed.require_publishable()


def test_source_tree_hash_ignores_runtime_cache_but_binds_paths(tmp_path):
    package = tmp_path / "groundnut"
    package.mkdir()
    source = package / "engine.py"
    source.write_text("RESULT = 1\n")
    first = source_tree_sha256(package)
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "engine.py").write_text("not shipped source")
    assert source_tree_sha256(package) == first

    source.rename(package / "renamed.py")
    assert source_tree_sha256(package) != first


def test_repository_identity_records_commit_dirty_state_and_source(tmp_path):
    import subprocess

    package = tmp_path / "groundnut"
    package.mkdir()
    source = package / "engine.py"
    source.write_text("RESULT = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Fixture"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "add", "groundnut/engine.py"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True
    )

    clean = EngineIdentity.from_repository(version="0.1", repository=tmp_path)
    assert clean.dirty is False
    assert clean.publishable is True

    source.write_text("RESULT = 2\n")
    dirty = EngineIdentity.from_repository(version="0.1", repository=tmp_path)
    assert dirty.revision == clean.revision
    assert dirty.dirty is True
    assert dirty.source_sha256 != clean.source_sha256

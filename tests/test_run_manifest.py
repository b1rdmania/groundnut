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
        engine=EngineIdentity(version="0.1", revision="5bee6ce"),
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
        EngineIdentity(version="0.1", revision="main")


def test_artifact_requires_schema_and_finite_canonical_json():
    with pytest.raises(ValueError, match="declare a schema"):
        ArtifactDigest.from_value("analysis", {"value": 1})
    with pytest.raises(ValueError, match="JSON compliant"):
        ArtifactDigest.from_value("analysis", {"schema": "x/v1", "value": float("nan")})

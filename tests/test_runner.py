import json

from groundnut.arena_emission import DEFAULT_ARENA_EMISSION_PROFILE
from groundnut.artifacts import DEFAULT_ARTIFACT_PROFILE
from groundnut.authority import AuthorityDeclaration, AuthorityPolicy
from groundnut.domain import Category, DomainPack
from groundnut.run_manifest import EngineIdentity
from groundnut.runner import execute_canonical_check, run_canonical_check
from groundnut.provenance import sha256_text
from groundnut.sources import (
    ResolvedSource,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceResolution,
)
from groundnut.support import ExactSupportDetector, SupportPolicy


SUPPORT_POLICY = SupportPolicy(
    key="exact",
    version="1",
    frozen_at="2026-08-17T00:00:00Z",
    detector=ExactSupportDetector.identity,
    min_confidence=1.0,
)
AUTHORITY_POLICY = AuthorityPolicy(
    key="authority",
    version="1",
    frozen_at="2026-08-17T00:00:00Z",
)
DOMAIN = DomainPack(
    key="claims",
    version="1",
    name="Claims",
    document_noun="document",
    extract_context="Extract claims.",
    classify_context="Classify evidence.",
    categories=(Category("claim", "Claim", 1),),
)
ENGINE = EngineIdentity(
    version="0.1",
    revision="abc123",
    source_sha256="a" * 64,
    dirty=False,
)


class FixtureResolver:
    def resolve(self, reference):
        return SourceResolution(
            source=ResolvedSource(
                reference=reference,
                text="Revenue for 2025 was $4.2 million.",
                fetched_at="2026-08-17T00:00:00Z",
            )
        )


def test_canonical_runner_composes_artifact_source_support_and_authority(tmp_path):
    artifact = tmp_path / "claims.json"
    artifact.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "revenue",
                        "claim_text": "Revenue for 2025 was $4.2 million.",
                        "source_url": "https://example.test/filing",
                        "source_excerpt": "Revenue for 2025 was $4.2 million.",
                    }
                ]
            }
        )
    )
    declaration = AuthorityDeclaration(
        kind="independent_primary",
        basis="human_adjudication",
        assigned_by="human:r1",
        note="Official filing reviewed.",
        source_id=f"url:{sha256_text('https://example.test/filing')[:16]}",
    )
    result = run_canonical_check(
        artifact,
        artifact_profile=DEFAULT_ARTIFACT_PROFILE,
        resolver=SnapshotFirstResolver(
            SnapshotStore(tmp_path / "snapshots"),
            FixtureResolver(),
            mode="snapshot_preferred",
        ),
        detector=ExactSupportDetector(),
        support_policy=SUPPORT_POLICY,
        authority_policy=AUTHORITY_POLICY,
        authority_declarations={"revenue": declaration},
    )
    payload = result.to_dict()
    assert payload["schema"] == "groundnut-canonical-run/v1"
    assert payload["acquisitions"][0]["strategy"] == "live_archived"
    assert payload["evidence"]["summary"]["support_status_counts"] == {
        "supported": 1
    }
    assert payload["evidence"]["complete_authority"] is True
    assert payload["arena"] is None
    assert len(payload["sha256"]) == 64


def test_canonical_runner_can_emit_arena_tasks_from_same_artifact(tmp_path):
    artifact = tmp_path / "report.html"
    artifact.write_text(
        "<section><p>Revenue for 2025 was $4.2 million "
        '<a href="https://example.test/filing">official filing</a>'
        "<!-- groundnut-source-quote: Revenue for 2025 was $4.2 million. --></p>"
        "<p>Therefore the company is likely to sustain this revenue level.</p></section>"
    )
    result = run_canonical_check(
        artifact,
        artifact_profile=DEFAULT_ARTIFACT_PROFILE,
        resolver=SnapshotFirstResolver(
            SnapshotStore(tmp_path / "snapshots"),
            FixtureResolver(),
            mode="snapshot_preferred",
        ),
        detector=ExactSupportDetector(),
        support_policy=SUPPORT_POLICY,
        authority_policy=AUTHORITY_POLICY,
        arena_profile=DEFAULT_ARENA_EMISSION_PROFILE,
    )
    assert result.arena is not None
    assert result.arena.tasks[0].trigger == "inferential"
    assert result.evidence.complete_authority is False


def test_canonical_runner_can_emit_arena_tasks_from_original_artifact(tmp_path):
    artifact = tmp_path / "claims.json"
    artifact.write_text(json.dumps({"claims": [{"claim_text": "Unsourced claim"}]}))
    original = tmp_path / "report.md"
    original.write_text(
        "Therefore the company is likely to sustain this revenue level for the next year."
    )
    result = run_canonical_check(
        artifact,
        artifact_profile=DEFAULT_ARTIFACT_PROFILE,
        resolver=SnapshotFirstResolver(SnapshotStore(tmp_path / "snapshots")),
        detector=ExactSupportDetector(),
        support_policy=SUPPORT_POLICY,
        authority_policy=AUTHORITY_POLICY,
        arena_profile=DEFAULT_ARENA_EMISSION_PROFILE,
        arena_artifact_path=original,
    )
    assert result.arena is not None
    assert result.arena.input_sha256 == sha256_text(original.read_text())
    assert result.arena.tasks[0].trigger == "inferential"


def test_execution_manifest_binds_engine_domain_policies_sources_and_run(tmp_path):
    artifact = tmp_path / "claims.json"
    artifact.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "revenue",
                        "claim_text": "Revenue for 2025 was $4.2 million.",
                        "source_url": "https://example.test/filing",
                    }
                ]
            }
        )
    )
    execution = execute_canonical_check(
        artifact,
        engine=ENGINE,
        domain=DOMAIN,
        artifact_profile=DEFAULT_ARTIFACT_PROFILE,
        resolver=SnapshotFirstResolver(
            SnapshotStore(tmp_path / "snapshots"),
            FixtureResolver(),
            mode="snapshot_preferred",
        ),
        detector=ExactSupportDetector(),
        support_policy=SUPPORT_POLICY,
        authority_policy=AUTHORITY_POLICY,
        publication_grade=True,
    )
    payload = execution.to_dict()
    assert payload["schema"] == "groundnut-canonical-execution/v1"
    assert payload["manifest"]["engine"]["source_sha256"] == "a" * 64
    assert payload["manifest"]["domain"]["key"] == "claims"
    assert {row["kind"] for row in payload["manifest"]["policies"]} == {
        "artifact_profile",
        "authority",
        "support",
    }
    assert payload["manifest"]["artifacts"][0]["kind"] == "canonical_run"
    assert len(payload["sha256"]) == 64


def test_publication_execution_rejects_dirty_engine(tmp_path):
    artifact = tmp_path / "claims.json"
    artifact.write_text(json.dumps({"claims": [{"claim_text": "Unsourced claim"}]}))
    dirty = EngineIdentity(
        version="0.1",
        revision="abc123",
        source_sha256="b" * 64,
        dirty=True,
    )
    import pytest

    with pytest.raises(ValueError, match="clean engine build"):
        execute_canonical_check(
            artifact,
            engine=dirty,
            domain=DOMAIN,
            artifact_profile=DEFAULT_ARTIFACT_PROFILE,
            resolver=SnapshotFirstResolver(SnapshotStore(tmp_path / "snapshots")),
            detector=ExactSupportDetector(),
            support_policy=SUPPORT_POLICY,
            authority_policy=AUTHORITY_POLICY,
            publication_grade=True,
        )

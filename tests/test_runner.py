import json

from groundnut.arena_emission import DEFAULT_ARENA_EMISSION_PROFILE
from groundnut.artifacts import DEFAULT_ARTIFACT_PROFILE
from groundnut.authority import AuthorityDeclaration, AuthorityPolicy
from groundnut.runner import run_canonical_check
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

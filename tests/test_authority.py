import pytest

from groundnut.authority import (
    AUTHORITY_KINDS,
    AuthorityDeclaration,
    AuthorityPolicy,
    ClaimEvidenceAccount,
    account_for_claim_check,
    assess_evidence_authority,
)
from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
from groundnut.checker import ClaimCheckReport
from groundnut.support import ExactSupportDetector, SupportPolicy, assess_claim_support
from groundnut.verification import Claim, verify_claim


REFERENCE = SourceReference("filing", "https://example.test/filing")
SOURCE = ResolvedSource(
    reference=REFERENCE,
    text="Revenue for 2025 was $4.2 million.",
    fetched_at="2026-08-17T00:00:00Z",
)
RESOLUTION = SourceResolution(source=SOURCE)
SUPPORT_POLICY = SupportPolicy(
    key="exact",
    version="1",
    frozen_at="2026-08-17T00:00:00Z",
    detector=ExactSupportDetector.identity,
    min_confidence=1.0,
)
AUTHORITY_POLICY = AuthorityPolicy(
    key="canonical-authority",
    version="1",
    frozen_at="2026-08-17T00:00:00Z",
)


def assessment(claim):
    verification = verify_claim(claim, RESOLUTION if claim.source else None)
    return assess_claim_support(
        verification,
        RESOLUTION if claim.source else None,
        detector=ExactSupportDetector(),
        policy=SUPPORT_POLICY,
    )


def declaration(kind, source_id="filing"):
    return AuthorityDeclaration(
        kind=kind,
        basis="human_adjudication",
        assigned_by="human:r1",
        note="Reviewed against the source publisher and provenance.",
        source_id=source_id,
    )


def test_same_supported_claim_retains_different_authority():
    checked = assessment(
        Claim(
            "revenue",
            "Revenue for 2025 was $4.2 million.",
            source=REFERENCE,
            excerpt="Revenue for 2025 was $4.2 million.",
        )
    )
    subject = assess_evidence_authority(
        checked,
        policy=AUTHORITY_POLICY,
        declaration=declaration("subject_provided"),
    )
    independent = assess_evidence_authority(
        checked,
        policy=AUTHORITY_POLICY,
        declaration=declaration("independent_primary"),
    )

    assert subject.assessment.support.status == "supported"
    assert independent.assessment.support.status == "supported"
    assert subject.authority.kind == "subject_provided"
    assert independent.authority.kind == "independent_primary"
    assert subject.to_dict()["schema"] == "groundnut-claim-evidence-account/v1"


def test_missing_authority_is_unknown_not_independent():
    checked = assessment(Claim("c1", "A claim", source=REFERENCE))
    account = assess_evidence_authority(checked, policy=AUTHORITY_POLICY)
    assert account.authority.kind == "unknown_authority"
    assert account.authority.basis == "unassigned"


def test_declared_analysis_is_analyst_derived_without_support_upgrade():
    checked = assessment(
        Claim("c1", "A bottom-up estimate.", declared_analysis=True)
    )
    account = assess_evidence_authority(checked, policy=AUTHORITY_POLICY)
    assert account.authority.kind == "analyst_derived"
    assert account.authority.basis == "artifact_declaration"
    assert account.assessment.support.status == "not_assessed"


def test_declaration_must_match_source_identity():
    checked = assessment(Claim("c1", "A claim", source=REFERENCE))
    with pytest.raises(ValueError, match="source does not match"):
        assess_evidence_authority(
            checked,
            policy=AUTHORITY_POLICY,
            declaration=declaration("independent_primary", source_id="other"),
        )


def test_policy_cannot_silently_remove_unknown_or_other_kinds():
    assert len(AUTHORITY_KINDS) == 5
    with pytest.raises(ValueError, match="complete canonical vocabulary"):
        AuthorityPolicy(
            key="narrow",
            version="1",
            frozen_at="2026-08-17T00:00:00Z",
            kinds=("independent_primary",),
        )


def test_account_rejects_claim_or_source_mismatch():
    checked = assessment(Claim("c1", "A claim", source=REFERENCE))
    account = assess_evidence_authority(checked, policy=AUTHORITY_POLICY)
    wrong = account.authority.__class__(
        **{**account.authority.__dict__, "claim_id": "other"}
    )
    with pytest.raises(ValueError, match="claim identities differ"):
        ClaimEvidenceAccount(checked, wrong)


def test_batch_report_keeps_support_and_authority_summaries_separate():
    first = assessment(
        Claim(
            "subject",
            "Revenue for 2025 was $4.2 million.",
            source=REFERENCE,
        )
    )
    second = assessment(
        Claim(
            "independent",
            "Revenue for 2025 was $4.2 million.",
            source=REFERENCE,
        )
    )
    support_report = ClaimCheckReport(
        policy_key=SUPPORT_POLICY.key,
        policy_sha256=SUPPORT_POLICY.sha256,
        claims=(first, second),
    )
    report = account_for_claim_check(
        support_report,
        policy=AUTHORITY_POLICY,
        declarations={
            "subject": declaration("subject_provided"),
            "independent": declaration("independent_primary"),
        },
    )
    payload = report.to_dict()
    assert payload["summary"]["support_status_counts"] == {"supported": 2}
    assert payload["summary"]["authority_kind_counts"]["subject_provided"] == 1
    assert payload["summary"]["authority_kind_counts"]["independent_primary"] == 1
    assert payload["complete_authority"] is True
    assert len(payload["sha256"]) == 64


def test_batch_report_rejects_unused_declarations():
    checked = assessment(Claim("known", "A claim", source=REFERENCE))
    support_report = ClaimCheckReport(
        policy_key=SUPPORT_POLICY.key,
        policy_sha256=SUPPORT_POLICY.sha256,
        claims=(checked,),
    )
    with pytest.raises(ValueError, match="unknown claims"):
        account_for_claim_check(
            support_report,
            policy=AUTHORITY_POLICY,
            declarations={"other": declaration("subject_provided")},
        )

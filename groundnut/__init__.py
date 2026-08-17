"""Groundnut's reusable document-intelligence engine.

``pipeline`` remains the compatibility CLI used by the original CUAD eval.
New integrations should build on the typed contracts exported here.
"""

from .domain import Category, DocumentType, DomainEvidence, DomainPack
from .artifacts import (
    ArtifactExtraction,
    ArtifactProfile,
    DEFAULT_ARTIFACT_PROFILE,
    extract_artifact,
)
from .engine import AnalysisResult, analyse_text
from .coverage import CheckCoverage, CoverageManifest
from .authority import (
    AUTHORITY_KINDS,
    AuthorityAssessment,
    AuthorityDeclaration,
    AuthorityPolicy,
    ClaimEvidenceAccount,
    ClaimEvidenceReport,
    account_for_claim_check,
    assess_evidence_authority,
)
from .provenance import SourceAnchor, SourceRecord, anchor_quote
from .sources import (
    FileResolver,
    HttpResolver,
    ResolvedSource,
    SnapshotStore,
    SnapshotFirstResolver,
    SourceAcquisition,
    SourceReference,
    SourceResolution,
)
from .arena import (
    ArenaPolicy,
    ArenaReport,
    ArenaTask,
    Attack,
    Ruling,
    adjudicate,
)
from .arena_emission import (
    ArenaEmissionProfile,
    ArenaTaskEmission,
    DEFAULT_ARENA_EMISSION_PROFILE,
    emit_arena_tasks,
)
from .registry import DomainRegistry
from .parity import ParityComparison, compare_analysis, semantic_projection
from .support import (
    ClaimAssessment,
    DetectorDecision,
    DetectorIdentity,
    ExactSupportDetector,
    SupportAssessment,
    SupportPolicy,
    SupportSpan,
    assess_claim_support,
)
from .support_eval import SupportGold, score_support
from .support_cases import CaseProvenance, SupportCase, SupportProbe
from .support_seeds import (
    AttestedSpanSeed,
    PresentIrrelevantCandidate,
    SeedImport,
    build_present_irrelevant_candidates,
    import_legalbenchrag,
    load_support_seeds,
    sample_present_irrelevant_candidates,
)
from .annotations import AnnotationBundle, EvidenceAnnotation
from .probe_plan import SupportProbePlan
from .support_admission import (
    RecordedProbeRun,
    SupportAdmissionReport,
    evaluate_support_admission,
)
from .support_bakeoff import SupportBakeoff, run_support_bakeoff
from .support_review import (
    PilotReviewManifest,
    PilotReviewRow,
    apply_review_decisions_tsv,
    build_pilot_probe,
    prepare_review_manifest,
    propose_negation_flip,
    review_decisions_tsv,
)
from .support_review_html import render_support_review_html
from .run_manifest import (
    ArtifactDigest,
    DomainDigest,
    EngineIdentity,
    PolicyDigest,
    RunManifest,
    RuntimeComponent,
    SourceDigest,
    source_tree_sha256,
)
from .checker import ClaimCheckReport, check_claims
from .runner import CanonicalRun, run_canonical_check
from .adapters import LettuceDetectAdapter, MiniCheckAdapter
from .support_runner import ProbeContextDigest, SupportProbeRun, run_support_probe
from .verification import (
    Claim,
    MatchOutcome,
    VerifiedClaim,
    anchor_excerpt,
    verification_metrics,
    verify_claim,
)

__all__ = [
    "AnalysisResult",
    "AUTHORITY_KINDS",
    "AnnotationBundle",
    "ArtifactDigest",
    "ArtifactExtraction",
    "ArtifactProfile",
    "AuthorityAssessment",
    "AuthorityDeclaration",
    "AuthorityPolicy",
    "AttestedSpanSeed",
    "ArenaPolicy",
    "ArenaEmissionProfile",
    "ArenaReport",
    "ArenaTask",
    "ArenaTaskEmission",
    "Attack",
    "Category",
    "CanonicalRun",
    "CaseProvenance",
    "Claim",
    "ClaimAssessment",
    "ClaimCheckReport",
    "ClaimEvidenceAccount",
    "ClaimEvidenceReport",
    "CheckCoverage",
    "CoverageManifest",
    "DocumentType",
    "DEFAULT_ARTIFACT_PROFILE",
    "DEFAULT_ARENA_EMISSION_PROFILE",
    "DomainDigest",
    "DetectorDecision",
    "DetectorIdentity",
    "DomainEvidence",
    "DomainPack",
    "DomainRegistry",
    "FileResolver",
    "ExactSupportDetector",
    "EngineIdentity",
    "EvidenceAnnotation",
    "HttpResolver",
    "MatchOutcome",
    "MiniCheckAdapter",
    "ParityComparison",
    "PresentIrrelevantCandidate",
    "PolicyDigest",
    "PilotReviewManifest",
    "PilotReviewRow",
    "ProbeContextDigest",
    "ResolvedSource",
    "RecordedProbeRun",
    "Ruling",
    "RunManifest",
    "RuntimeComponent",
    "SnapshotStore",
    "SnapshotFirstResolver",
    "SourceAcquisition",
    "SourceAnchor",
    "SourceDigest",
    "source_tree_sha256",
    "SourceReference",
    "SourceRecord",
    "SourceResolution",
    "SeedImport",
    "SupportAssessment",
    "SupportAdmissionReport",
    "SupportBakeoff",
    "SupportCase",
    "SupportGold",
    "SupportPolicy",
    "SupportProbe",
    "SupportProbePlan",
    "SupportProbeRun",
    "SupportSpan",
    "VerifiedClaim",
    "LettuceDetectAdapter",
    "analyse_text",
    "account_for_claim_check",
    "adjudicate",
    "assess_claim_support",
    "assess_evidence_authority",
    "anchor_quote",
    "apply_review_decisions_tsv",
    "anchor_excerpt",
    "compare_analysis",
    "check_claims",
    "build_present_irrelevant_candidates",
    "build_pilot_probe",
    "import_legalbenchrag",
    "evaluate_support_admission",
    "emit_arena_tasks",
    "extract_artifact",
    "load_support_seeds",
    "prepare_review_manifest",
    "propose_negation_flip",
    "review_decisions_tsv",
    "render_support_review_html",
    "run_support_bakeoff",
    "sample_present_irrelevant_candidates",
    "semantic_projection",
    "score_support",
    "run_support_probe",
    "run_canonical_check",
    "verification_metrics",
    "verify_claim",
]

"""Groundnut's reusable document-intelligence engine.

``pipeline`` remains the compatibility CLI used by the original CUAD eval.
New integrations should build on the typed contracts exported here.
"""

from .domain import Category, DocumentType, DomainEvidence, DomainPack
from .engine import AnalysisResult, analyse_text
from .coverage import CheckCoverage, CoverageManifest
from .provenance import SourceAnchor, SourceRecord, anchor_quote
from .sources import (
    FileResolver,
    HttpResolver,
    ResolvedSource,
    SnapshotStore,
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
from .run_manifest import (
    ArtifactDigest,
    DomainDigest,
    EngineIdentity,
    PolicyDigest,
    RunManifest,
    RuntimeComponent,
    SourceDigest,
)
from .checker import ClaimCheckReport, check_claims
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
    "AnnotationBundle",
    "ArtifactDigest",
    "AttestedSpanSeed",
    "ArenaPolicy",
    "ArenaReport",
    "ArenaTask",
    "Attack",
    "Category",
    "CaseProvenance",
    "Claim",
    "ClaimAssessment",
    "ClaimCheckReport",
    "CheckCoverage",
    "CoverageManifest",
    "DocumentType",
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
    "ProbeContextDigest",
    "ResolvedSource",
    "Ruling",
    "RunManifest",
    "RuntimeComponent",
    "SnapshotStore",
    "SourceAnchor",
    "SourceDigest",
    "SourceReference",
    "SourceRecord",
    "SourceResolution",
    "SeedImport",
    "SupportAssessment",
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
    "adjudicate",
    "assess_claim_support",
    "anchor_quote",
    "anchor_excerpt",
    "compare_analysis",
    "check_claims",
    "build_present_irrelevant_candidates",
    "import_legalbenchrag",
    "load_support_seeds",
    "sample_present_irrelevant_candidates",
    "semantic_projection",
    "score_support",
    "run_support_probe",
    "verification_metrics",
    "verify_claim",
]

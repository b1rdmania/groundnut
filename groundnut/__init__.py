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
from .support_cases import SupportCase, SupportProbe
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
    "ArtifactDigest",
    "ArenaPolicy",
    "ArenaReport",
    "ArenaTask",
    "Attack",
    "Category",
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
    "HttpResolver",
    "MatchOutcome",
    "ParityComparison",
    "PolicyDigest",
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
    "SupportAssessment",
    "SupportCase",
    "SupportGold",
    "SupportPolicy",
    "SupportProbe",
    "SupportSpan",
    "VerifiedClaim",
    "analyse_text",
    "adjudicate",
    "assess_claim_support",
    "anchor_quote",
    "anchor_excerpt",
    "compare_analysis",
    "check_claims",
    "semantic_projection",
    "score_support",
    "verification_metrics",
    "verify_claim",
]

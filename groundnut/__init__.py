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
    "ArenaPolicy",
    "ArenaReport",
    "ArenaTask",
    "Attack",
    "Category",
    "Claim",
    "CheckCoverage",
    "CoverageManifest",
    "DocumentType",
    "DomainEvidence",
    "DomainPack",
    "DomainRegistry",
    "FileResolver",
    "HttpResolver",
    "MatchOutcome",
    "ParityComparison",
    "ResolvedSource",
    "Ruling",
    "SnapshotStore",
    "SourceAnchor",
    "SourceReference",
    "SourceRecord",
    "SourceResolution",
    "VerifiedClaim",
    "analyse_text",
    "adjudicate",
    "anchor_quote",
    "anchor_excerpt",
    "compare_analysis",
    "semantic_projection",
    "verification_metrics",
    "verify_claim",
]

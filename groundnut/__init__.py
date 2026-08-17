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

__all__ = [
    "AnalysisResult",
    "ArenaPolicy",
    "ArenaReport",
    "ArenaTask",
    "Attack",
    "Category",
    "CheckCoverage",
    "CoverageManifest",
    "DocumentType",
    "DomainEvidence",
    "DomainPack",
    "FileResolver",
    "HttpResolver",
    "ResolvedSource",
    "Ruling",
    "SnapshotStore",
    "SourceAnchor",
    "SourceReference",
    "SourceRecord",
    "SourceResolution",
    "analyse_text",
    "adjudicate",
    "anchor_quote",
]

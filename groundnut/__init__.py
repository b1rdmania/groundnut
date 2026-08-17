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

__all__ = [
    "AnalysisResult",
    "Category",
    "CheckCoverage",
    "CoverageManifest",
    "DocumentType",
    "DomainEvidence",
    "DomainPack",
    "FileResolver",
    "HttpResolver",
    "ResolvedSource",
    "SnapshotStore",
    "SourceAnchor",
    "SourceReference",
    "SourceRecord",
    "SourceResolution",
    "analyse_text",
    "anchor_quote",
]

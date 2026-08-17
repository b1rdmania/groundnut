"""Groundnut's reusable document-intelligence engine.

``pipeline`` remains the compatibility CLI used by the original CUAD eval.
New integrations should build on the typed contracts exported here.
"""

from .domain import Category, DocumentType, DomainEvidence, DomainPack
from .engine import AnalysisResult, analyse_text
from .provenance import SourceAnchor, SourceRecord, anchor_quote

__all__ = [
    "AnalysisResult",
    "Category",
    "DocumentType",
    "DomainEvidence",
    "DomainPack",
    "SourceAnchor",
    "SourceRecord",
    "analyse_text",
    "anchor_quote",
]

"""Pure orchestration for checklist-driven, source-anchored extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline.chunking import chunk_text
from pipeline.extract import filter_verbatim, merge_findings, parse_response
from pipeline.prompt import build_prompt

from .domain import DomainPack
from .provenance import SourceAnchor, SourceRecord, anchor_quote


@dataclass(frozen=True)
class AnchoredFinding:
    category_key: str
    category_name: str
    severity: int
    quote: str
    anchor: SourceAnchor

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_key": self.category_key,
            "category_name": self.category_name,
            "severity": self.severity,
            "quote": self.quote,
            "anchor": self.anchor.to_dict(),
        }


@dataclass(frozen=True)
class AnalysisResult:
    domain_key: str
    domain_version: str
    playbook_sha256: str
    manifest_sha256: str
    evidence_status: str
    evidence_disclosure: str
    source: SourceRecord
    segments_total: int
    findings: dict[str, list[str]]
    anchored_findings: tuple[AnchoredFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-analysis/v1",
            "domain": {
                "key": self.domain_key,
                "version": self.domain_version,
                "playbook_sha256": self.playbook_sha256,
                "manifest_sha256": self.manifest_sha256,
                "evidence_status": self.evidence_status,
                "evidence_disclosure": self.evidence_disclosure,
            },
            "source": {
                "source_id": self.source.source_id,
                "sha256": self.source.sha256,
                "characters": self.source.characters,
            },
            "segments_total": self.segments_total,
            "findings": self.findings,
            "anchored_findings": [row.to_dict() for row in self.anchored_findings],
        }


def analyse_text(
    text: str,
    *,
    source_id: str,
    domain: DomainPack,
    backend,
) -> AnalysisResult:
    """Run one domain pack over one source and return anchored findings."""
    chunks = chunk_text(text)
    chunk_results = []
    for chunk in chunks:
        prompt = build_prompt(domain.category_names, chunk, domain=domain)
        raw = backend.complete(prompt, doc_id=source_id)
        chunk_results.append(filter_verbatim(parse_response(raw), chunk))

    findings = merge_findings(chunk_results, domain.category_names)
    by_name = {category.name: category for category in domain.categories}
    anchored = []
    for category_name, quotes in findings.items():
        category = by_name[category_name]
        for quote in quotes:
            anchored.append(
                AnchoredFinding(
                    category_key=category.key,
                    category_name=category.name,
                    severity=category.severity,
                    quote=quote,
                    anchor=anchor_quote(source_id, text, quote),
                )
            )

    return AnalysisResult(
        domain_key=domain.key,
        domain_version=domain.version,
        playbook_sha256=domain.playbook_sha256,
        manifest_sha256=domain.manifest_sha256,
        evidence_status=domain.evidence.status,
        evidence_disclosure=domain.evidence.disclosure,
        source=SourceRecord.from_text(source_id, text),
        segments_total=len(chunks),
        findings=findings,
        anchored_findings=tuple(anchored),
    )

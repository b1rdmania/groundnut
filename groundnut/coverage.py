"""Deterministic, fail-closed coverage accounting.

No finding is not the same as a clear check. A category is ``checked_clear``
only when every source segment completed and explicitly acknowledged that
category. This is the portable invariant behind Atlas's coverage matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .domain import DomainPack


@dataclass(frozen=True)
class CheckCoverage:
    category_key: str
    category_name: str
    severity: int
    status: str
    coverage_complete: bool
    segments_total: int
    segments_completed: int
    segments_checked: int
    finding_count: int

    def to_dict(self) -> dict:
        return {
            "category_key": self.category_key,
            "category_name": self.category_name,
            "severity": self.severity,
            "status": self.status,
            "coverage_complete": self.coverage_complete,
            "segments_total": self.segments_total,
            "segments_completed": self.segments_completed,
            "segments_checked": self.segments_checked,
            "finding_count": self.finding_count,
        }


@dataclass(frozen=True)
class CoverageManifest:
    complete: bool
    segments_total: int
    segments_completed: int
    checks: tuple[CheckCoverage, ...]
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        counts: dict[str, int] = {}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return {
            "complete": self.complete,
            "segments_total": self.segments_total,
            "segments_completed": self.segments_completed,
            "status_counts": counts,
            "errors": list(self.errors),
            "checks": [check.to_dict() for check in self.checks],
        }


def build_coverage(
    domain: DomainPack,
    *,
    segment_checks: Iterable[set[str] | None],
    findings: dict[str, list[str]],
    errors: Iterable[str] = (),
) -> CoverageManifest:
    """Build per-category coverage from one acknowledgement set per segment.

    ``None`` means the segment did not complete or its response could not be
    parsed. Unknown category names never count as acknowledgements.
    """
    segment_checks = tuple(segment_checks)
    errors = tuple(errors)
    segments_total = len(segment_checks)
    segments_completed = sum(row is not None for row in segment_checks)
    checks = []
    for category in domain.categories:
        segments_checked = sum(
            row is not None and category.name in row for row in segment_checks
        )
        finding_count = len(findings.get(category.name, []))
        coverage_complete = (
            segments_total > 0
            and segments_completed == segments_total
            and segments_checked == segments_total
        )
        if finding_count:
            status = "risk_found"
        elif coverage_complete:
            status = "checked_clear"
        else:
            status = "incomplete"
        checks.append(
            CheckCoverage(
                category_key=category.key,
                category_name=category.name,
                severity=category.severity,
                status=status,
                coverage_complete=coverage_complete,
                segments_total=segments_total,
                segments_completed=segments_completed,
                segments_checked=segments_checked,
                finding_count=finding_count,
            )
        )
    complete = not errors and all(check.coverage_complete for check in checks)
    return CoverageManifest(
        complete=complete,
        segments_total=segments_total,
        segments_completed=segments_completed,
        checks=tuple(checks),
        errors=errors,
    )

"""Small, deterministic Markdown population scanner.

This is deliberately not a Markdown renderer. It classifies physical lines,
surfaces malformed frontmatter/fences, and exposes claim-bearing prose/table
cells to both canonical extraction and the claim ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_HR = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_TABLE_ROW = re.compile(r"^\s*\|")
_TABLE_DELIMITER_CELL = re.compile(r"^:?-{3,}:?$")
_FENCE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})")


@dataclass(frozen=True)
class PopulationAnomaly:
    code: str
    line: int

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "line": self.line}


@dataclass(frozen=True)
class MarkdownPopulation:
    total_lines: int
    included_lines: tuple[tuple[str, int], ...]
    excluded_lines: tuple[tuple[str, int], ...]
    anomalies: tuple[PopulationAnomaly, ...]

    def __post_init__(self) -> None:
        included = dict(self.included_lines)
        excluded = dict(self.excluded_lines)
        if len(included) != len(self.included_lines) or len(excluded) != len(
            self.excluded_lines
        ):
            raise ValueError("population line classes must be unique")
        if any(value < 0 for value in (*included.values(), *excluded.values())):
            raise ValueError("population line counts cannot be negative")
        if sum(included.values()) + sum(excluded.values()) != self.total_lines:
            raise ValueError("population accounting must cover every physical line")

    def to_dict(self, *, units: int) -> dict[str, object]:
        status = "malformed" if self.anomalies else "observed" if units else "empty"
        return {
            "schema": "groundnut-markdown-population/v1",
            "status": status,
            "units": units,
            "total_lines": self.total_lines,
            "included_lines": dict(self.included_lines),
            "excluded_lines": dict(self.excluded_lines),
            "anomalies": [row.to_dict() for row in self.anomalies],
        }


@dataclass(frozen=True)
class MarkdownContentLine:
    line: int
    kind: str
    segments: tuple[str, ...]


def scan_markdown(text: str) -> tuple[tuple[MarkdownContentLine, ...], MarkdownPopulation]:
    """Return claim-bearing segments and an auditable physical-line tally."""

    lines = text.splitlines()
    included: dict[str, int] = {}
    excluded: dict[str, int] = {}
    anomalies: list[PopulationAnomaly] = []
    content: list[MarkdownContentLine] = []

    frontmatter_end: int | None = None
    if lines and lines[0].strip() == "---":
        frontmatter_end = next(
            (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
            None,
        )
        if frontmatter_end is None:
            anomalies.append(PopulationAnomaly("unclosed_frontmatter", 1))

    table_headers: set[int] = set()
    table_delimiters: set[int] = set()
    table_bodies: set[int] = set()
    for delimiter in range(1, len(lines)):
        if not (
            _looks_like_table_row(lines[delimiter - 1])
            and _is_table_delimiter(lines[delimiter])
        ):
            continue
        table_headers.add(delimiter - 1)
        table_delimiters.add(delimiter)
        body = delimiter + 1
        while body < len(lines) and _looks_like_table_row(lines[body]):
            table_bodies.add(body)
            body += 1

    fence_marker: str | None = None
    fence_open_line: int | None = None
    for index, line in enumerate(lines):
        number = index + 1
        stripped = line.strip()

        if lines and lines[0].strip() == "---" and (
            frontmatter_end is None or index <= frontmatter_end
        ):
            _count(excluded, "frontmatter")
            continue

        fence = _FENCE.match(line)
        if fence_marker is not None:
            if fence and _closes_fence(fence.group("marker"), fence_marker):
                _count(excluded, "fence_delimiter")
                fence_marker = None
                fence_open_line = None
            else:
                _count(excluded, "fenced_code")
            continue
        if fence:
            fence_marker = fence.group("marker")
            fence_open_line = number
            _count(excluded, "fence_delimiter")
            continue

        if not stripped:
            _count(excluded, "blank")
        elif index in table_headers:
            _count(excluded, "table_header")
        elif index in table_delimiters or _is_table_delimiter(line):
            _count(excluded, "table_delimiter")
        elif index in table_bodies or _TABLE_ROW.match(line):
            cells = _table_cells(line)
            if cells:
                _count(included, "table_row")
                content.append(MarkdownContentLine(number, "table_row", cells))
            else:
                _count(excluded, "empty_table_row")
        elif _HEADING.match(line):
            _count(excluded, "heading")
        elif _HR.match(line):
            _count(excluded, "horizontal_rule")
        else:
            _count(included, "prose")
            content.append(MarkdownContentLine(number, "prose", (line,)))

    if fence_marker is not None and fence_open_line is not None:
        anomalies.append(PopulationAnomaly("unclosed_fence", fence_open_line))

    population = MarkdownPopulation(
        total_lines=len(lines),
        included_lines=tuple(sorted(included.items())),
        excluded_lines=tuple(sorted(excluded.items())),
        anomalies=tuple(anomalies),
    )
    return tuple(content), population


def _table_cells(line: str) -> tuple[str, ...]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|") and not value.endswith(r"\|"):
        value = value[:-1]
    cells = re.split(r"(?<!\\)\|", value)
    return tuple(cell.replace(r"\|", "|").strip() for cell in cells if cell.strip())


def _is_table_delimiter(line: str) -> bool:
    if "|" not in line:
        return False
    cells = _table_cells(line)
    return bool(cells) and all(_TABLE_DELIMITER_CELL.fullmatch(cell) for cell in cells)


def _looks_like_table_row(line: str) -> bool:
    return "|" in line and bool(_table_cells(line))


def _closes_fence(candidate: str, opening: str) -> bool:
    return candidate[0] == opening[0] and len(candidate) >= len(opening)


def _count(rows: dict[str, int], key: str) -> None:
    rows[key] = rows.get(key, 0) + 1

"""Deterministic extraction of adversarial-review tasks from artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .arena import ArenaTask
from .provenance import sha256_text


_SECTION = "GROUNDNUTSECTIONBOUNDARY"
_META = re.compile(
    r"^(prepared (?:by|for)\b|data cutoff|confidential\b|©|page \d)|"
    r"\bthis (?:report|document|section|page) (?:will|suggests)\b",
    re.I,
)


@dataclass(frozen=True)
class ArenaEmissionProfile:
    key: str
    version: str
    inferential_patterns: tuple[str, ...] = (
        r"\btherefore\b",
        r"\b(?:thus|hence)\b",
        r"\bthis (?:means|implies|suggests|indicates)\b",
        r"\b(?:suggests?|implies?|likely|unlikely|probably)\b",
        r"\bwe (?:believe|assess|estimate|expect|conclude)\b",
        r"\b(?:positioned|poised|on track) to\b",
        r"\b(?:appears?|seems?) (?:to|that)\b",
        r"\bdepends? (?:entirely|heavily|largely) on\b",
    )
    derived_patterns: tuple[str, ...] = (
        r"\breconstruct\w*\b",
        r"\bbottom[-\s]?up estimate\w*\b",
        r"\bextrapolat\w*\b",
        r"\bannuali[sz]\w*\b",
        r"\brun[-\s]?rate\b",
        r"\bimplied (?:actual )?(?:revenue|cost|margin|rate|throughput|capacity|valuation|value|multiple)\b",
        r"\b(?:needs?|requires?)\s+(?:(?:a|an)\s+)?~?\d+(?:\.\d+)?\s?[x×](?=\s|$|[.,;:])",
    )
    absence_patterns: tuple[str, ...] = (
        r"\b(?:with\s+)?no\s+(?:(?:named|identified|documented)\s+)?(?:successor|record|filing|award|contract|plan|financials?|audit\w*|registration|disclosure|renewal)\b",
        r"\bno\s+(?:[\w-]+\s+){1,3}(?:on record|on file|filed|disclosed|found|identified|recorded)\b",
        r"\bnot (?:found|listed|disclosed|recorded) (?:in|on|at)\b",
        r"\bnothing (?:on record|filed|disclosed)\b",
    )
    min_characters: int = 30
    max_characters: int = 500
    context_max_sentences: int = 14
    context_max_characters: int = 2400

    def __post_init__(self) -> None:
        object.__setattr__(self, "inferential_patterns", tuple(self.inferential_patterns))
        object.__setattr__(self, "derived_patterns", tuple(self.derived_patterns))
        object.__setattr__(self, "absence_patterns", tuple(self.absence_patterns))
        if not self.key.strip() or not self.version.strip():
            raise ValueError("arena emission profile identity is required")
        if not all((self.inferential_patterns, self.derived_patterns, self.absence_patterns)):
            raise ValueError("arena emission profile requires all trigger classes")
        if self.min_characters < 1 or self.max_characters < self.min_characters:
            raise ValueError("arena emission character bounds are invalid")
        if self.context_max_sentences < 1 or self.context_max_characters < 1:
            raise ValueError("arena emission context bounds must be positive")
        for pattern in self.inferential_patterns + self.derived_patterns + self.absence_patterns:
            re.compile(pattern)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-arena-emission-profile/v1",
            "key": self.key,
            "version": self.version,
            "patterns": {
                "inferential": list(self.inferential_patterns),
                "derived": list(self.derived_patterns),
                "absence": list(self.absence_patterns),
            },
            "bounds": {
                "min_characters": self.min_characters,
                "max_characters": self.max_characters,
                "context_max_sentences": self.context_max_sentences,
                "context_max_characters": self.context_max_characters,
            },
        }

    @property
    def sha256(self) -> str:
        value = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(value).hexdigest()


DEFAULT_ARENA_EMISSION_PROFILE = ArenaEmissionProfile(
    key="groundnut-conclusions", version="1"
)


@dataclass(frozen=True)
class ArenaTaskEmission:
    input_sha256: str
    profile_key: str
    profile_sha256: str
    tasks: tuple[ArenaTask, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-arena-task-emission/v1",
            "input_sha256": self.input_sha256,
            "profile": {"key": self.profile_key, "sha256": self.profile_sha256},
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class _Sentence:
    text: str
    section: int
    ordinal: int


def emit_arena_tasks(
    path: str | Path,
    profile: ArenaEmissionProfile = DEFAULT_ARENA_EMISSION_PROFILE,
) -> ArenaTaskEmission:
    artifact = Path(path)
    raw = artifact.read_text()
    suffix = artifact.suffix.casefold()
    if suffix in {".html", ".htm"}:
        sentences = _sentences(raw, html=True)
    elif suffix in {".md", ".markdown", ".txt"}:
        sentences = _sentences(raw, html=False)
    else:
        raise ValueError(f"unsupported arena artifact suffix: {suffix or '<none>'}")
    tasks = []
    seen = set()
    for index, sentence in enumerate(sentences):
        if not profile.min_characters <= len(sentence.text) <= profile.max_characters:
            continue
        if _META.search(sentence.text):
            continue
        trigger = _trigger(sentence.text, profile)
        if trigger is None:
            continue
        key = _normalise(sentence.text)
        if key in seen:
            continue
        seen.add(key)
        tasks.append(
            ArenaTask(
                task_id=f"x{len(tasks) + 1}",
                assertion=sentence.text,
                context=_context(sentences, index, profile),
                location=f"sentence {sentence.ordinal}, section {sentence.section}",
                trigger=trigger,
                section=sentence.section,
            )
        )
    return ArenaTaskEmission(
        input_sha256=sha256_text(raw),
        profile_key=profile.key,
        profile_sha256=profile.sha256,
        tasks=tuple(tasks),
    )


def _sentences(raw: str, *, html: bool) -> list[_Sentence]:
    if html:
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
        text = re.sub(r"<(?:section|article)\b[^>]*>", f"\n{_SECTION}", text, flags=re.I)
        text = re.sub(
            r"<div\b[^>]*class=[\"'][^\"']*\bslide\b[^\"']*[\"'][^>]*>",
            f"\n{_SECTION}",
            text,
            flags=re.I,
        )
        text = re.sub(r"<h[1-6]\b[^>]*>", f"\n{_SECTION}", text, flags=re.I)
        text = re.sub(
            r"</(?:p|div|li|h[1-6]|td|th|tr|section|article|header|footer|blockquote)>",
            "\n",
            text,
            flags=re.I,
        )
        text = re.sub(r"<(?:br|hr)\s*/?>", "\n", text, flags=re.I)
        text = unescape(re.sub(r"<[^>]+>", " ", text))
    else:
        text = re.sub(r"^#{1,6}\s+", f"{_SECTION}", raw, flags=re.M)
        text = re.sub(r"\[([^\]]+)\]\((?:https?://[^\s)\"]+)(?:\s+\"[^\"]*\")?\)", r"\1", text)
        text = re.sub(r"[*_`>|]", " ", text)
    output = []
    section = 0
    ordinal = 0
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if line.startswith(_SECTION):
            section += 1
            line = line[len(_SECTION) :].strip()
            if not line:
                continue
        for value in re.split(r"(?<=[.!?])\s+(?=[A-Z$£€0-9'\"])", line):
            clean = value.strip()
            if len(clean) >= 8:
                ordinal += 1
                output.append(_Sentence(clean, section, ordinal))
    return output


def _trigger(text: str, profile: ArenaEmissionProfile) -> str | None:
    for label, patterns in (
        ("absence", profile.absence_patterns),
        ("derived", profile.derived_patterns),
        ("inferential", profile.inferential_patterns),
    ):
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            return label
    return None


def _context(
    sentences: list[_Sentence], index: int, profile: ArenaEmissionProfile
) -> str:
    target = sentences[index]
    nearby = [
        (abs(row_index - index), row_index, row)
        for row_index, row in enumerate(sentences)
        if row.section == target.section and row_index != index
    ]
    selected = []
    characters = 0
    for _, row_index, row in sorted(nearby):
        if len(selected) >= profile.context_max_sentences:
            break
        if characters + len(row.text) > profile.context_max_characters:
            continue
        selected.append((row_index, row.text))
        characters += len(row.text)
    return " ".join(text for _, text in sorted(selected))


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%$£€]+", " ", value.casefold()).split())

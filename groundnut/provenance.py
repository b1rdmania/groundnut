"""Source records and anchors shared by extraction and verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


_WS = re.compile(r"\s+")
_TRANS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


def normalise_text(value: str) -> str:
    return _WS.sub(" ", value.translate(_TRANS)).strip().casefold()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    sha256: str
    characters: int

    @classmethod
    def from_text(cls, source_id: str, text: str) -> "SourceRecord":
        return cls(source_id=source_id, sha256=sha256_text(text), characters=len(text))


@dataclass(frozen=True)
class SourceAnchor:
    source_id: str
    source_sha256: str
    quote: str
    exact: bool
    normalised: bool
    offsets: tuple[tuple[int, int], ...]

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "quote": self.quote,
            "exact": self.exact,
            "normalised": self.normalised,
            "offsets": [list(pair) for pair in self.offsets],
        }


def _all_offsets(source: str, quote: str) -> tuple[tuple[int, int], ...]:
    if not quote:
        return ()
    found = []
    start = 0
    while True:
        index = source.find(quote, start)
        if index < 0:
            return tuple(found)
        found.append((index, index + len(quote)))
        start = index + max(len(quote), 1)


def anchor_quote(source_id: str, source_text: str, quote: str) -> SourceAnchor:
    """Anchor a quote without conflating exact and tolerant grounding.

    Character offsets are emitted only for exact substrings. A normalised
    match remains useful evidence, but it is not represented as a verbatim
    source location.
    """
    offsets = _all_offsets(source_text, quote)
    normalised_quote = normalise_text(quote)
    return SourceAnchor(
        source_id=source_id,
        source_sha256=sha256_text(source_text),
        quote=quote,
        exact=bool(offsets),
        normalised=bool(normalised_quote)
        and normalised_quote in normalise_text(source_text),
        offsets=offsets,
    )

"""Filesystem registry for versioned Groundnut domain packs."""

from __future__ import annotations

from pathlib import Path

from .domain import DomainPack


class DomainRegistry:
    def __init__(self, packs: list[DomainPack] | tuple[DomainPack, ...]) -> None:
        self._packs: dict[str, DomainPack] = {}
        for pack in packs:
            if pack.key in self._packs:
                raise ValueError(f"duplicate domain key: {pack.key}")
            self._packs[pack.key] = pack

    @classmethod
    def from_directory(cls, directory: str | Path) -> "DomainRegistry":
        directory = Path(directory)
        return cls([DomainPack.from_json(path) for path in sorted(directory.glob("*.json"))])

    def get(self, key: str) -> DomainPack:
        try:
            return self._packs[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._packs)) or "none"
            raise KeyError(f"unknown domain {key!r}; available: {available}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._packs))

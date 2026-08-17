"""Conservative agent-only screening that cannot qualify the support gate."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .support_review import PilotReviewManifest


SUGGESTION_SCHEMA = "groundnut-support-agent-suggestion/v1"
SCREEN_SCHEMA = "groundnut-support-agent-screen/v1"
_DECISIONS = {"accepted", "rejected", "ambiguous"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class AgentSuggestion:
    input_sha256: str
    agent: str
    irrelevant_decision: str
    irrelevant_note: str
    paraphrase_text: str
    paraphrase_note: str
    paraphrase_lexical_overlap: float
    paraphrase_absent_from_context: bool
    contradiction_decision: str
    contradiction_note: str
    requires_human_review: bool

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.input_sha256,
                self.agent,
                self.irrelevant_note,
                self.paraphrase_text,
                self.paraphrase_note,
                self.contradiction_note,
            )
        ):
            raise ValueError("agent suggestion identity and text are required")
        if not _SHA256.fullmatch(self.input_sha256):
            raise ValueError("agent suggestion input hash must be lowercase sha256")
        if self.irrelevant_decision not in _DECISIONS:
            raise ValueError("invalid agent irrelevance decision")
        if self.contradiction_decision not in _DECISIONS:
            raise ValueError("invalid agent contradiction decision")
        if not 0 <= self.paraphrase_lexical_overlap <= 1:
            raise ValueError("agent paraphrase overlap must be between zero and one")
        if not self.requires_human_review:
            raise ValueError("agent suggestions must retain the human-review warning")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AgentSuggestion":
        if value.get("schema") != SUGGESTION_SCHEMA:
            raise ValueError(f"unsupported agent suggestion schema: {value.get('schema')}")
        absent = value["paraphrase_absent_from_context"]
        requires_review = value["requires_human_review"]
        if not isinstance(absent, bool) or not isinstance(requires_review, bool):
            raise ValueError("agent suggestion flags must be booleans")
        return cls(
            input_sha256=str(value["input_sha256"]),
            agent=str(value["agent"]),
            irrelevant_decision=str(value["irrelevant_decision"]),
            irrelevant_note=str(value["irrelevant_note"]),
            paraphrase_text=str(value["paraphrase_text"]),
            paraphrase_note=str(value["paraphrase_note"]),
            paraphrase_lexical_overlap=float(value["paraphrase_lexical_overlap"]),
            paraphrase_absent_from_context=absent,
            contradiction_decision=str(value["contradiction_decision"]),
            contradiction_note=str(value["contradiction_note"]),
            requires_human_review=requires_review,
        )


@dataclass(frozen=True)
class AgentSupportScreen:
    manifest_sha256: str
    target_group_count: int
    agents: tuple[str, ...]
    included_input_sha256: tuple[str, ...]
    excluded: tuple[tuple[str, tuple[str, ...]], ...]

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": SCREEN_SCHEMA,
            "qualification": "exploratory_only",
            "eligible_for_admission": False,
            "disclosure": (
                "Agent-screened development material. It is not human-adjudicated "
                "gold and cannot qualify a detector for canonical admission."
            ),
            "review_manifest_sha256": self.manifest_sha256,
            "target_group_count": self.target_group_count,
            "agents": list(self.agents),
            "included_group_count": len(self.included_input_sha256),
            "included_case_count": 4 * len(self.included_input_sha256),
            "included_input_sha256": list(self.included_input_sha256),
            "excluded": [
                {"input_sha256": digest, "reasons": list(reasons)}
                for digest, reasons in self.excluded
            ],
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def screen_agent_suggestions(
    manifest: PilotReviewManifest,
    suggestions: Iterable[AgentSuggestion],
) -> AgentSupportScreen:
    """Select structurally complete agent drafts without promoting them to gold."""

    targets = manifest.rows[: manifest.target_group_count]
    suggestion_rows = tuple(suggestions)
    by_hash = {row.input_sha256: row for row in suggestion_rows}
    if len(by_hash) != len(suggestion_rows):
        raise ValueError("duplicate agent suggestion input hash")
    expected = {row.input_sha256 for row in targets}
    if set(by_hash) != expected:
        raise ValueError("agent suggestions must cover exactly the frozen target rows")
    included = []
    excluded = []
    for row in targets:
        suggestion = by_hash[row.input_sha256]
        reasons = []
        if suggestion.irrelevant_decision != "accepted":
            reasons.append(f"irrelevance_{suggestion.irrelevant_decision}")
        if suggestion.contradiction_decision != "accepted":
            reasons.append(f"contradiction_{suggestion.contradiction_decision}")
        if not (
            manifest.lexical_overlap_min
            <= suggestion.paraphrase_lexical_overlap
            <= manifest.lexical_overlap_max
        ):
            reasons.append("paraphrase_overlap_outside_frozen_band")
        if not suggestion.paraphrase_absent_from_context:
            reasons.append("paraphrase_present_in_context")
        if reasons:
            excluded.append((row.input_sha256, tuple(reasons)))
        else:
            included.append(row.input_sha256)
    return AgentSupportScreen(
        manifest_sha256=manifest.sha256,
        target_group_count=manifest.target_group_count,
        agents=tuple(sorted({row.agent for row in by_hash.values()})),
        included_input_sha256=tuple(included),
        excluded=tuple(excluded),
    )

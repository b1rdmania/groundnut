"""Frozen preregistration contract for a semantic-support probe."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from typing import Mapping


PLAN_SCHEMA = "groundnut-support-probe-plan/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SupportProbePlan:
    key: str
    frozen_at: str
    group_count: int
    sampling_seed: int
    probe_sha256: str
    source_pool_sha256: str
    excluded_pool_sha256: str
    max_context_characters: int
    primary_metric: str
    minimum_improvement: float
    baseline_policy_keys: tuple[str, ...]
    detector_policy_keys: tuple[str, ...]
    lexical_overlap_min: float
    lexical_overlap_max: float
    schema: str = PLAN_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_policy_keys", tuple(self.baseline_policy_keys))
        object.__setattr__(self, "detector_policy_keys", tuple(self.detector_policy_keys))
        if self.schema != PLAN_SCHEMA:
            raise ValueError(f"unsupported support-probe plan schema: {self.schema}")
        if not all(value.strip() for value in (self.key, self.frozen_at, self.primary_metric)):
            raise ValueError("probe plan identity fields are required")
        if self.group_count <= 0 or self.max_context_characters <= 0:
            raise ValueError("probe plan sizes must be positive")
        if not all(
            _SHA256.fullmatch(value)
            for value in (
                self.probe_sha256,
                self.source_pool_sha256,
                self.excluded_pool_sha256,
            )
        ):
            raise ValueError("probe plan probe/pool hashes must be lowercase SHA-256")
        if not self.baseline_policy_keys or not self.detector_policy_keys:
            raise ValueError("probe plan must freeze baseline and detector policies")
        if self.minimum_improvement <= 0:
            raise ValueError("probe plan minimum improvement must be positive")
        if not 0 <= self.lexical_overlap_min < self.lexical_overlap_max <= 1:
            raise ValueError("probe plan lexical-overlap bounds are invalid")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "key": self.key,
            "frozen_at": self.frozen_at,
            "group_count": self.group_count,
            "sampling_seed": self.sampling_seed,
            "probe_sha256": self.probe_sha256,
            "source_pool_sha256": self.source_pool_sha256,
            "excluded_pool_sha256": self.excluded_pool_sha256,
            "max_context_characters": self.max_context_characters,
            "primary_metric": self.primary_metric,
            "minimum_improvement": self.minimum_improvement,
            "baseline_policy_keys": sorted(self.baseline_policy_keys),
            "detector_policy_keys": sorted(self.detector_policy_keys),
            "lexical_overlap_min": self.lexical_overlap_min,
            "lexical_overlap_max": self.lexical_overlap_max,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def validate_probe(self, probe_sha256: str, group_count: int) -> None:
        if not _SHA256.fullmatch(probe_sha256):
            raise ValueError("probe hash must be lowercase SHA-256")
        if probe_sha256 != self.probe_sha256:
            raise ValueError("probe hash differs from frozen plan")
        if group_count != self.group_count:
            raise ValueError(
                f"probe group count differs from frozen plan: {group_count} != {self.group_count}"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SupportProbePlan":
        return cls(
            schema=str(value.get("schema", PLAN_SCHEMA)),
            key=str(value["key"]),
            frozen_at=str(value["frozen_at"]),
            group_count=int(value["group_count"]),
            sampling_seed=int(value["sampling_seed"]),
            probe_sha256=str(value["probe_sha256"]),
            source_pool_sha256=str(value["source_pool_sha256"]),
            excluded_pool_sha256=str(value["excluded_pool_sha256"]),
            max_context_characters=int(value["max_context_characters"]),
            primary_metric=str(value["primary_metric"]),
            minimum_improvement=float(value["minimum_improvement"]),
            baseline_policy_keys=tuple(str(item) for item in value["baseline_policy_keys"]),
            detector_policy_keys=tuple(str(item) for item in value["detector_policy_keys"]),
            lexical_overlap_min=float(value["lexical_overlap_min"]),
            lexical_overlap_max=float(value["lexical_overlap_max"]),
        )

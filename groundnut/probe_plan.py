"""Frozen preregistration contract for a semantic-support probe."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from typing import Mapping


PLAN_SCHEMA = "groundnut-support-probe-plan/v3"
PRIMARY_METRICS = frozenset({"macro_f1", "accuracy"})
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
    review_manifest_sha256: str
    build_attempt: int
    contexts_sha256: str
    max_context_characters: int
    primary_metric: str
    minimum_improvement: float
    baseline_policy_keys: tuple[str, ...]
    detector_policy_keys: tuple[str, ...]
    policy_hashes: tuple[tuple[str, str], ...]
    lexical_overlap_min: float
    lexical_overlap_max: float
    schema: str = PLAN_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_policy_keys", tuple(self.baseline_policy_keys))
        object.__setattr__(self, "detector_policy_keys", tuple(self.detector_policy_keys))
        hashes = (
            self.policy_hashes.items()
            if isinstance(self.policy_hashes, Mapping)
            else self.policy_hashes
        )
        object.__setattr__(
            self,
            "policy_hashes",
            tuple(sorted((str(key), str(digest)) for key, digest in hashes)),
        )
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
                self.review_manifest_sha256,
                self.contexts_sha256,
            )
        ):
            raise ValueError(
                "probe plan probe/pool/manifest/context hashes must be lowercase SHA-256"
            )
        if self.build_attempt < 1:
            raise ValueError("probe plan build attempt must be at least 1")
        if self.primary_metric not in PRIMARY_METRICS:
            raise ValueError(f"unsupported admission primary metric: {self.primary_metric}")
        if not self.baseline_policy_keys or not self.detector_policy_keys:
            raise ValueError("probe plan must freeze baseline and detector policies")
        all_policy_keys = self.baseline_policy_keys + self.detector_policy_keys
        if any(not key.strip() for key in all_policy_keys):
            raise ValueError("probe plan policy keys cannot be blank")
        if len(all_policy_keys) != len(set(all_policy_keys)):
            raise ValueError("probe plan baseline and detector policy keys must be distinct")
        hash_keys = [key for key, _ in self.policy_hashes]
        if len(hash_keys) != len(set(hash_keys)) or set(hash_keys) != set(all_policy_keys):
            raise ValueError("probe plan must bind one hash for every policy key")
        if any(not _SHA256.fullmatch(digest) for _, digest in self.policy_hashes):
            raise ValueError("probe plan policy hashes must be lowercase SHA-256")
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
            "review_manifest_sha256": self.review_manifest_sha256,
            "build_attempt": self.build_attempt,
            "contexts_sha256": self.contexts_sha256,
            "max_context_characters": self.max_context_characters,
            "primary_metric": self.primary_metric,
            "minimum_improvement": self.minimum_improvement,
            "baseline_policy_keys": sorted(self.baseline_policy_keys),
            "detector_policy_keys": sorted(self.detector_policy_keys),
            "policy_hashes": dict(self.policy_hashes),
            "lexical_overlap_min": self.lexical_overlap_min,
            "lexical_overlap_max": self.lexical_overlap_max,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}

    def validate_probe(self, probe_sha256: str, group_count: int) -> None:
        if not _SHA256.fullmatch(probe_sha256):
            raise ValueError("probe hash must be lowercase SHA-256")
        if probe_sha256 != self.probe_sha256:
            raise ValueError("probe hash differs from frozen plan")
        if group_count != self.group_count:
            raise ValueError(
                f"probe group count differs from frozen plan: {group_count} != {self.group_count}"
            )

    def policy_sha256(self, key: str) -> str:
        try:
            return dict(self.policy_hashes)[key]
        except KeyError as error:
            raise ValueError(f"policy is not frozen in probe plan: {key}") from error

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
            review_manifest_sha256=str(value["review_manifest_sha256"]),
            build_attempt=int(value["build_attempt"]),
            contexts_sha256=str(value["contexts_sha256"]),
            max_context_characters=int(value["max_context_characters"]),
            primary_metric=str(value["primary_metric"]),
            minimum_improvement=float(value["minimum_improvement"]),
            baseline_policy_keys=tuple(str(item) for item in value["baseline_policy_keys"]),
            detector_policy_keys=tuple(str(item) for item in value["detector_policy_keys"]),
            policy_hashes=tuple(
                (str(key), str(digest))
                for key, digest in value["policy_hashes"].items()
            ),
            lexical_overlap_min=float(value["lexical_overlap_min"]),
            lexical_overlap_max=float(value["lexical_overlap_max"]),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "SupportProbePlan":
        value = json.loads(Path(path).read_text())
        plan = cls.from_mapping(value)
        if value.get("sha256") is not None and value["sha256"] != plan.sha256:
            raise ValueError("support-probe plan self-hash mismatch")
        return plan

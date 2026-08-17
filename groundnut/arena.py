"""Policy-driven, fail-closed adversarial review.

The core runner is deliberately mechanical: it validates tasks, attacks, and
rulings supplied by humans or model adapters. It never calls a model and never
turns disagreement or missing work into an exoneration.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


POLICY_SCHEMA = "groundnut-arena-policy/v1"
VERDICTS = {
    "flagged",
    "contested",
    "stands",
    "withheld",
    "unruled",
    "unattacked",
}


@dataclass(frozen=True)
class ArenaPolicy:
    key: str
    version: str
    frozen_at: str
    lenses: tuple[str, ...]
    required_rulings: int = 2
    schema: str = POLICY_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "lenses", tuple(self.lenses))
        if self.schema != POLICY_SCHEMA:
            raise ValueError(f"unsupported arena policy schema: {self.schema}")
        if not self.key or not self.version or not self.frozen_at:
            raise ValueError("arena policy identity and frozen_at are required")
        if not self.lenses or len(self.lenses) != len(set(self.lenses)):
            raise ValueError("arena policy lenses must be non-empty and unique")
        if self.required_rulings < 1:
            raise ValueError("required_rulings must be positive")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "key": self.key,
            "version": self.version,
            "frozen_at": self.frozen_at,
            "lenses": list(self.lenses),
            "required_rulings": self.required_rulings,
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_json(cls, path: str | Path) -> "ArenaPolicy":
        value = json.loads(Path(path).read_text())
        return cls(
            schema=str(value.get("schema", POLICY_SCHEMA)),
            key=str(value["key"]),
            version=str(value["version"]),
            frozen_at=str(value["frozen_at"]),
            lenses=tuple(str(row) for row in value["lenses"]),
            required_rulings=int(value.get("required_rulings", 2)),
        )


@dataclass(frozen=True)
class ArenaTask:
    task_id: str
    assertion: str
    context: str
    location: str


@dataclass(frozen=True)
class Attack:
    task_id: str
    lens: str
    attack: str | None
    severity: str | None
    model: str
    model_family: str
    session_id: str
    premise_probe: str | None = None

    def __post_init__(self) -> None:
        if self.attack is None and (self.severity is not None or self.premise_probe is not None):
            raise ValueError("null attack cannot carry severity or premise_probe")
        if self.attack is not None and self.severity not in {"fatal", "material", "minor"}:
            raise ValueError("non-null attack requires fatal, material, or minor severity")


@dataclass(frozen=True)
class Ruling:
    task_id: str
    lens: str
    ruling: str
    reason: str
    model: str
    model_family: str
    session_id: str

    def __post_init__(self) -> None:
        if self.ruling not in {"lands", "glances", "misses"}:
            raise ValueError(f"unknown arena ruling: {self.ruling}")


@dataclass(frozen=True)
class AttackResult:
    attack: Attack
    rulings: tuple[Ruling, ...]
    consensus: str


@dataclass(frozen=True)
class ArenaFinding:
    task: ArenaTask
    verdict: str
    attacks: tuple[AttackResult, ...]


@dataclass(frozen=True)
class ArenaReport:
    policy_key: str
    policy_sha256: str
    passed: bool
    withheld_density: float | None
    findings: tuple[ArenaFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        totals = {verdict: 0 for verdict in sorted(VERDICTS)}
        for finding in self.findings:
            totals[finding.verdict] += 1
        return {
            "schema": "groundnut-arena-report/v1",
            "policy": {"key": self.policy_key, "sha256": self.policy_sha256},
            "passed": self.passed,
            "withheld_density": self.withheld_density,
            "totals": {"tasks": len(self.findings), **totals},
            "findings": [
                {
                    "task": {
                        "task_id": row.task.task_id,
                        "assertion": row.task.assertion,
                        "context": row.task.context,
                        "location": row.task.location,
                    },
                    "verdict": row.verdict,
                    "attacks": [
                        {
                            "lens": result.attack.lens,
                            "attack": result.attack.attack,
                            "severity": result.attack.severity,
                            "consensus": result.consensus,
                            "rulings": [
                                {
                                    "ruling": ruling.ruling,
                                    "reason": ruling.reason,
                                    "model": ruling.model,
                                    "model_family": ruling.model_family,
                                    "session_id": ruling.session_id,
                                }
                                for ruling in result.rulings
                            ],
                        }
                        for result in row.attacks
                    ],
                }
                for row in self.findings
            ],
        }


def adjudicate(
    policy: ArenaPolicy,
    tasks: list[ArenaTask],
    attacks: list[Attack],
    rulings: list[Ruling],
) -> ArenaReport:
    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("duplicate arena task id")
    known_tasks = set(task_ids)
    attack_index: dict[tuple[str, str], Attack] = {}
    for attack in attacks:
        if attack.task_id not in known_tasks:
            raise ValueError(f"attack references unknown task: {attack.task_id}")
        if attack.lens not in policy.lenses:
            raise ValueError(f"attack uses lens outside frozen policy: {attack.lens}")
        key = (attack.task_id, attack.lens)
        if key in attack_index:
            raise ValueError(f"duplicate attack row: {key}")
        attack_index[key] = attack

    ruling_index: dict[tuple[str, str], list[Ruling]] = {}
    for ruling in rulings:
        key = (ruling.task_id, ruling.lens)
        attack = attack_index.get(key)
        if attack is None or attack.attack is None:
            raise ValueError(f"ruling has no non-null attack: {key}")
        if ruling.session_id == attack.session_id:
            raise ValueError(f"attacker cannot rule on its own attack: {key}")
        ruling_index.setdefault(key, []).append(ruling)

    findings = []
    for task in tasks:
        task_attacks = [
            attack_index[(task.task_id, lens)]
            for lens in policy.lenses
            if (task.task_id, lens) in attack_index
        ]
        results = []
        for attack in task_attacks:
            mine = tuple(ruling_index.get((task.task_id, attack.lens), []))
            consensus = "not_required" if attack.attack is None else _consensus(policy, mine)
            results.append(AttackResult(attack=attack, rulings=mine, consensus=consensus))

        if not task_attacks:
            verdict = "unattacked"
        elif len(task_attacks) != len(policy.lenses):
            verdict = "unruled"
        elif any(result.consensus == "incomplete" for result in results):
            verdict = "unruled"
        elif any(result.consensus == "lands" for result in results):
            verdict = "flagged"
        elif any(result.consensus == "glances" for result in results):
            verdict = "contested"
        elif any(result.consensus == "disagrees" for result in results):
            verdict = "withheld"
        else:
            verdict = "stands"
        findings.append(
            ArenaFinding(task=task, verdict=verdict, attacks=tuple(results))
        )

    withheld = sum(row.verdict == "withheld" for row in findings)
    density = withheld / len(findings) if findings else None
    passed = bool(findings) and all(row.verdict == "stands" for row in findings)
    return ArenaReport(
        policy_key=policy.key,
        policy_sha256=policy.sha256,
        passed=passed,
        withheld_density=density,
        findings=tuple(findings),
    )


def _consensus(policy: ArenaPolicy, rulings: tuple[Ruling, ...]) -> str:
    if len(rulings) != policy.required_rulings:
        return "incomplete"
    if len({row.model_family for row in rulings}) != policy.required_rulings:
        return "incomplete"
    if len({row.session_id for row in rulings}) != policy.required_rulings:
        return "incomplete"
    values = {row.ruling for row in rulings}
    return next(iter(values)) if len(values) == 1 else "disagrees"

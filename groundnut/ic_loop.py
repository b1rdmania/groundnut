"""One command for the IC research loop: report in, claim ledger out.

    python3 -m groundnut.ic_loop --report research/research-report.md --out groundnut/

Writes, under --out:

    request.json   the canonical request that was executed (replayable)
    run.json       the canonical response, hash-bound
    ledger.json    the three-bucket claim ledger
    ledger.md      the readable ledger
    gate.json      the numeric gate result and any bound human waiver
    snapshots/     every source fetched, so the run replays offline

By default sources are fetched live once and snapshotted (``snapshot_preferred``);
pass ``--replay-only`` to refuse the network. The IC domain pack and artifact
profile are the repository's ``domains/ic_research.json`` and
``profiles/ic-research-pipeline.json``; both are experimental and carry no
quality claim.
"""

from __future__ import annotations

import argparse
from importlib.resources import files
import json
from pathlib import Path
from typing import Any

from .artifacts import ArtifactProfile
from .canonical_cli import RESPONSE_SCHEMA, execute_request
from .ledger import build_claim_ledger, render_ledger_markdown, undeclared_numeric_rows
from .waivers import GateWaiver

_DATA = files("groundnut").joinpath("data")
DEFAULT_DOMAIN = Path(str(_DATA.joinpath("domains", "ic_research.json")))
DEFAULT_PROFILE = Path(str(_DATA.joinpath("profiles", "ic-research-pipeline.json")))
DEFAULT_SUPPORT_POLICY = Path(
    str(_DATA.joinpath("policies", "exact-support-baseline-v1.json"))
)
class GateFailure(ValueError):
    """The report failed a preflight gate; the run itself is valid."""


AUTHORITY_POLICY = {
    "schema": "groundnut-authority-policy/v1",
    "key": "ic_shadow_authority",
    "version": "0.1.0-shadow",
    "frozen_at": "2026-08-17T00:00:00Z",
}


def build_request(
    report: Path,
    out: Path,
    *,
    domain: Path = DEFAULT_DOMAIN,
    profile: Path = DEFAULT_PROFILE,
    support_policy: Path = DEFAULT_SUPPORT_POLICY,
    replay_only: bool = False,
) -> dict[str, Any]:
    try:
        artifact_path = str(report.resolve().relative_to(out.resolve()))
    except ValueError:
        artifact_path = str(report.resolve())
    return {
        "schema": "groundnut-canonical-request/v1",
        "artifact": artifact_path,
        "arena_artifact": artifact_path,
        "snapshot_directory": "snapshots",
        "domain": json.loads(domain.read_text()),
        "artifact_profile": json.loads(profile.read_text()),
        "support_policy": json.loads(support_policy.read_text()),
        "authority_policy": AUTHORITY_POLICY,
        "arena_profile": True,
        "acquisition_mode": "replay_only" if replay_only else "snapshot_preferred",
        "publication_grade": False,
    }


def run_loop(
    report: Path,
    out: Path,
    *,
    title: str | None = None,
    replay_only: bool = False,
    gate_undeclared_numerics: bool = False,
    waiver_path: Path | None = None,
    domain: Path = DEFAULT_DOMAIN,
    profile: Path = DEFAULT_PROFILE,
    support_policy: Path = DEFAULT_SUPPORT_POLICY,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report_text = report.read_text()
    bundled_report = out / "input" / "report.md"
    bundled_report.parent.mkdir(parents=True, exist_ok=True)
    bundled_report.write_text(report_text)
    request = build_request(
        bundled_report, out, domain=domain, profile=profile, support_policy=support_policy,
        replay_only=replay_only,
    )
    response = execute_request(request, base_directory=out, allow_live=not replay_only)
    if response.get("schema") != RESPONSE_SCHEMA:
        raise ValueError(f"canonical engine returned {response.get('schema')}: {response}")
    ledger = build_claim_ledger(
        response,
        report_text,
        profile=ArtifactProfile.from_mapping(request["artifact_profile"]),
    )
    undeclared = undeclared_numeric_rows(ledger)
    incomplete_windows = tuple(
        row
        for row in ledger.rows
        if row.detail == "evidence_window_incomplete"
    )
    population = ledger.population.to_dict(units=len(ledger.rows))
    waiver = None
    gate_status = "not_requested"
    if waiver_path is not None and not gate_undeclared_numerics:
        raise ValueError("a waiver may be supplied only with --gate-undeclared-numerics")
    if gate_undeclared_numerics:
        if population["status"] != "observed":
            if waiver_path is not None:
                raise ValueError("a waiver cannot approve an indeterminate claim population")
            gate_status = "indeterminate"
        elif not undeclared:
            if waiver_path is not None:
                raise ValueError("waiver supplied but the gate has no failing units")
            gate_status = "clear"
        elif waiver_path is None:
            gate_status = "failed"
        else:
            waiver = GateWaiver.from_mapping(json.loads(waiver_path.read_text()))
            expected_ids = tuple(sorted(row.unit_id for row in undeclared))
            if waiver.artifact_sha256 != ledger.artifact_sha256:
                raise ValueError("waiver artifact_sha256 does not match this report")
            if waiver.ledger_sha256 != ledger.sha256:
                raise ValueError("waiver ledger_sha256 does not match this ledger")
            if waiver.waived_unit_ids != expected_ids:
                raise ValueError("waiver unit ids do not exactly match the failing gate units")
            gate_status = "waived"
    gate_receipt = {
        "schema": "groundnut-gate-receipt/v1",
        "gate": "undeclared_numeric_own_reasoning",
        "enabled": gate_undeclared_numerics,
        "status": gate_status,
        "artifact_sha256": ledger.artifact_sha256,
        "ledger_sha256": ledger.sha256,
        "failing_unit_ids": [row.unit_id for row in undeclared],
        "population": population,
        "annotation_conflicts": [
            {
                "unit_id": row.unit_id,
                "codes": list(row.annotation_conflicts),
            }
            for row in ledger.rows
            if row.annotation_conflicts
        ],
        "evidence_window_incomplete_unit_ids": [
            row.unit_id for row in incomplete_windows
        ],
        "waiver": waiver.to_dict() if waiver else None,
    }
    outputs = {
        "request.json": json.dumps(request, indent=2, sort_keys=True) + "\n",
        "run.json": json.dumps(response, indent=2, sort_keys=True) + "\n",
        "ledger.json": json.dumps(ledger.to_dict(), indent=2, sort_keys=True) + "\n",
        "ledger.md": render_ledger_markdown(
            ledger, title=title or f"Claim ledger — {report.stem}"
        ),
        "gate.json": json.dumps(gate_receipt, indent=2, sort_keys=True) + "\n",
    }
    for name, content in outputs.items():
        (out / name).write_text(content)
    counts = ledger.counts
    if gate_status == "indeterminate":
        raise GateFailure(
            "claim population is indeterminate: "
            f"status={population['status']}, units={population['units']}, "
            f"anomalies={population['anomalies']}"
        )
    if gate_status == "failed":
        lines = "\n".join(
            f"  {row.unit_id} L{row.line}: {row.text[:140]}" for row in undeclared
        )
        raise GateFailure(
            f"undeclared numeric own-reasoning units: {len(undeclared)}\n{lines}\n"
            "Fix in the report source: cite each number, or mark the sentence as "
            "declared analysis. Do not delete numbers to satisfy the gate."
        )
    return {
        "report": str(report),
        "out": str(out),
        "run_sha256": ledger.run_sha256,
        "ledger_sha256": ledger.sha256,
        "units": counts["units"],
        **counts["by_bucket"],
        "undeclared_numerics": len(undeclared),
        "population_status": population["status"],
        "annotation_conflicts": counts["annotation_conflicts"],
        "evidence_window_incomplete": len(incomplete_windows),
        "gate_status": gate_status,
        "waiver_sha256": waiver.sha256 if waiver else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument(
        "--gate-undeclared-numerics",
        action="store_true",
        help="exit 1 when any own-reasoning unit carries a number without a declared-analysis marker",
    )
    parser.add_argument(
        "--waiver",
        type=Path,
        help="human-approved groundnut-gate-waiver/v1 JSON matching the current failed ledger",
    )
    parser.add_argument("--domain", type=Path, default=DEFAULT_DOMAIN)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--support-policy", type=Path, default=DEFAULT_SUPPORT_POLICY)
    args = parser.parse_args(argv)
    try:
        summary = run_loop(
            args.report, args.out, title=args.title, replay_only=args.replay_only,
            gate_undeclared_numerics=args.gate_undeclared_numerics,
            waiver_path=args.waiver,
            domain=args.domain, profile=args.profile, support_policy=args.support_policy,
        )
    except GateFailure as error:
        print(f"GATE FAIL: {error}")
        return 1
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

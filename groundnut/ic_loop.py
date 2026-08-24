"""One command for the IC research loop: report in, claim ledger out.

    python3 -m groundnut.ic_loop --report research/research-report.md --out groundnut/

Writes, under --out:

    request.json   the canonical request that was executed (replayable)
    run.json       the canonical response, hash-bound
    ledger.json    the three-bucket claim ledger
    ledger.md      the readable ledger
    snapshots/     every source fetched, so the run replays offline

By default sources are fetched live once and snapshotted (``snapshot_preferred``);
pass ``--replay-only`` to refuse the network. The IC domain pack and artifact
profile are the repository's ``domains/ic_research.json`` and
``profiles/ic-research-pipeline.json``; both are experimental and carry no
quality claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .artifacts import ArtifactProfile
from .canonical_cli import RESPONSE_SCHEMA, execute_request
from .ledger import build_claim_ledger, render_ledger_markdown

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOMAIN = _ROOT / "domains" / "ic_research.json"
DEFAULT_PROFILE = _ROOT / "profiles" / "ic-research-pipeline.json"
DEFAULT_SUPPORT_POLICY = _ROOT / "policies" / "exact-support-baseline-v1.json"
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
    return {
        "schema": "groundnut-canonical-request/v1",
        "artifact": str(report.resolve()),
        "arena_artifact": str(report.resolve()),
        "snapshot_directory": str((out / "snapshots").resolve()),
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
    domain: Path = DEFAULT_DOMAIN,
    profile: Path = DEFAULT_PROFILE,
    support_policy: Path = DEFAULT_SUPPORT_POLICY,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    request = build_request(
        report, out, domain=domain, profile=profile, support_policy=support_policy,
        replay_only=replay_only,
    )
    response = execute_request(request, base_directory=out, allow_live=not replay_only)
    if response.get("schema") != RESPONSE_SCHEMA:
        raise ValueError(f"canonical engine returned {response.get('schema')}: {response}")
    ledger = build_claim_ledger(
        response,
        report.read_text(),
        profile=ArtifactProfile.from_mapping(request["artifact_profile"]),
    )
    outputs = {
        "request.json": json.dumps(request, indent=2, sort_keys=True) + "\n",
        "run.json": json.dumps(response, indent=2, sort_keys=True) + "\n",
        "ledger.json": json.dumps(ledger.to_dict(), indent=2, sort_keys=True) + "\n",
        "ledger.md": render_ledger_markdown(
            ledger, title=title or f"Claim ledger — {report.stem}"
        ),
    }
    for name, content in outputs.items():
        (out / name).write_text(content)
    counts = ledger.counts
    return {
        "report": str(report),
        "out": str(out),
        "run_sha256": ledger.run_sha256,
        "ledger_sha256": ledger.sha256,
        "units": counts["units"],
        **counts["by_bucket"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument("--domain", type=Path, default=DEFAULT_DOMAIN)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--support-policy", type=Path, default=DEFAULT_SUPPORT_POLICY)
    args = parser.parse_args(argv)
    try:
        summary = run_loop(
            args.report, args.out, title=args.title, replay_only=args.replay_only,
            domain=args.domain, profile=args.profile, support_policy=args.support_policy,
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

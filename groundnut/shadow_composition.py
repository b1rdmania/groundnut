"""Fail-closed composition of mechanical and experimental claim signals.

This module does not turn component agreement into truth. It records distinct
observations and explains why Groundnut did or did not issue a claim-checking
outcome under an explicit shadow policy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


SHADOW_COMPOSITION_SCHEMA = "groundnut-shadow-composition/v1"
SHADOW_POLICY_SCHEMA = "groundnut-shadow-policy/v1"
SHADOW_OUTCOMES = {
    "not_assessed",
    "source_unavailable",
    "needs_validation",
    "withheld",
}


def compose_shadow_receipt(
    accounts: Sequence[Mapping[str, Any]],
    *,
    component_signals: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    policy_key: str = "pre-admission-shadow",
    policy_version: str = "1",
) -> dict[str, Any]:
    """Compose observations without inventing thresholds or semantic authority."""

    signals = component_signals or {}
    rows = [
        _compose_account(account, tuple(signals.get(_claim_id(account), ())))
        for account in accounts
    ]
    rows.sort(key=lambda row: row["claim_id"])
    if len({row["claim_id"] for row in rows}) != len(rows):
        raise ValueError("shadow composition claim ids must be unique")
    policy = {
        "schema": SHADOW_POLICY_SCHEMA,
        "key": policy_key,
        "version": policy_version,
        "admitted_semantic_components": [],
        "rules": [
            "source failure remains source_unavailable",
            "a missing or inconclusive anchor remains needs_validation",
            "question-dependent judging abstains without an explicit verification question",
            "unadmitted component signals remain observations and cannot determine an outcome",
            "component scores are never averaged into truth",
        ],
    }
    policy["sha256"] = _sha256(policy)
    counts = {outcome: 0 for outcome in sorted(SHADOW_OUTCOMES)}
    for row in rows:
        counts[row["outcome"]] += 1
    payload = {
        "schema": SHADOW_COMPOSITION_SCHEMA,
        "policy": policy,
        "claim_count": len(rows),
        "outcomes": counts,
        "questions_present": sum(row["question_present"] for row in rows),
        "claims_with_experimental_signals": sum(
            bool(row["experimental_signals"]) for row in rows
        ),
        "disclosure": (
            "Shadow output only. No semantic component is admitted. The receipt "
            "preserves observations and abstentions; it does not establish truth."
        ),
        "rows": rows,
    }
    return {**payload, "sha256": _sha256(payload)}


def validate_shadow_receipt(value: Mapping[str, Any]) -> None:
    if value.get("schema") != SHADOW_COMPOSITION_SCHEMA:
        raise ValueError("unsupported shadow composition schema")
    payload = {key: row for key, row in value.items() if key != "sha256"}
    if value.get("sha256") != _sha256(payload):
        raise ValueError("shadow composition self-hash mismatch")
    rows = value.get("rows")
    if not isinstance(rows, list) or any(
        not isinstance(row, Mapping) or row.get("outcome") not in SHADOW_OUTCOMES
        for row in rows
    ):
        raise ValueError("shadow composition contains invalid rows")


def _claim_id(account: Mapping[str, Any]) -> str:
    try:
        value = account["assessment"]["verification"]["claim"]["claim_id"]
    except (KeyError, TypeError) as error:
        raise ValueError("account lacks a claim id") from error
    if not isinstance(value, str) or not value.strip():
        raise ValueError("account claim id must be a non-empty string")
    return value


def _compose_account(
    account: Mapping[str, Any], experimental_signals: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    claim_id = _claim_id(account)
    assessment = account.get("assessment")
    if not isinstance(assessment, Mapping):
        raise ValueError(f"{claim_id}: account assessment must be an object")
    verification = assessment.get("verification")
    support = assessment.get("support")
    if not isinstance(verification, Mapping) or not isinstance(support, Mapping):
        raise ValueError(f"{claim_id}: account lacks verification or support")
    claim = verification.get("claim")
    if not isinstance(claim, Mapping):
        raise ValueError(f"{claim_id}: verification lacks claim")

    source = claim.get("source")
    question = claim.get("question")
    question_present = isinstance(question, str) and bool(question.strip())
    anchor = verification.get("anchor")
    failure = verification.get("failure")
    if source is None:
        outcome, reason = "not_assessed", "claim_has_no_external_source"
    elif failure is not None or verification.get("method") == "fetch_failed":
        outcome, reason = "source_unavailable", str(failure or "source_unreachable")
    elif anchor != "found":
        outcome, reason = "needs_validation", f"anchor_{anchor or 'not_assessed'}"
    elif not question_present:
        outcome, reason = "withheld", "missing_verification_question"
    else:
        outcome, reason = "withheld", "no_semantic_component_admitted"

    preserved_signals = []
    for signal in experimental_signals:
        if not isinstance(signal, Mapping):
            raise ValueError(f"{claim_id}: experimental signal must be an object")
        preserved_signals.append(dict(signal))

    return {
        "claim_id": claim_id,
        "outcome": outcome,
        "reason": reason,
        "question_present": question_present,
        "mechanical_anchor": {
            "anchor": anchor,
            "method": verification.get("method"),
            "score": verification.get("score"),
            "failure": failure,
        },
        "exact_support_baseline": {
            "status": support.get("status"),
            "decision": support.get("decision"),
            "detector": support.get("detector"),
        },
        "experimental_signals": preserved_signals,
        "semantic_disagreement": {
            "state": "not_evaluated",
            "reason": "no semantic thresholds or components are admitted",
        },
    }


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()

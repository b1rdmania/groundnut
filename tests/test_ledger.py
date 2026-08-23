import json
from pathlib import Path

import pytest

from groundnut.canonical_cli import execute_request
from groundnut.ledger import (
    BUCKETS,
    LedgerSegmenter,
    build_claim_ledger,
    render_ledger_markdown,
)
from groundnut.ledger_cli import main as ledger_main
from groundnut.provenance import sha256_text
from groundnut.sources import ResolvedSource, SnapshotStore, SourceReference

ROOT = Path(__file__).parent.parent

REPORT = """---
title: Example memo
---

# Section 1

Opening remark that is short.

The company reported that [revenue was 4.2 million](https://example.test/filing "Source") <!-- groundnut-source-quote: Revenue was 4.2 million. --> in the last filing.

The company also said [headcount doubled](https://example.test/filing "Source") <!-- groundnut-source-quote: Headcount tripled in the period. --> over the same period. From that we infer the team will reach forty people by the end of next year.

At a $26,000 price and $20,000 of switching cost the condition requires value above $184,000 per year. The founders are clearly capable of executing on this plan in our view.

- A list item that stands alone as one unit of reasoning without any source.

| table | row |
|---|---|
"""


def _run(tmp_path):
    artifact = tmp_path / "report.md"
    artifact.write_text(REPORT)
    store = SnapshotStore(tmp_path / "snapshots")
    store.archive(
        ResolvedSource(
            reference=SourceReference(
                source_id=f"url:{sha256_text('https://example.test/filing')[:16]}",
                uri="https://example.test/filing",
            ),
            text="Annual report. Revenue was 4.2 million. Headcount grew.",
            fetched_at="2026-08-17T00:00:00Z",
        )
    )
    request = {
        "schema": "groundnut-canonical-request/v1",
        "artifact": str(artifact),
        "snapshot_directory": str(tmp_path / "snapshots"),
        "domain": str(ROOT / "domains" / "ma_dd.json"),
        "support_policy": str(ROOT / "policies" / "exact-support-baseline-v1.json"),
        "authority_policy": {
            "schema": "groundnut-authority-policy/v1",
            "key": "canonical_authority",
            "version": "1",
            "frozen_at": "2026-08-17T00:00:00Z",
        },
        "arena_profile": False,
    }
    return artifact, execute_request(request, base_directory=tmp_path)


def test_ledger_puts_every_prose_unit_in_exactly_one_bucket(tmp_path):
    artifact, execution = _run(tmp_path)
    ledger = build_claim_ledger(execution, artifact.read_text())

    by_detail = ledger.counts["by_detail"]
    assert ledger.counts["units"] == 6
    assert by_detail == {
        "cited_verified:found": 1,
        "cited_drifted:quote_not_found": 1,
        "own_reasoning:numeric": 1,
        "own_reasoning:narrative": 3,
    }
    inferred = [row for row in ledger.rows if row.text.startswith("From that we infer")]
    assert inferred and inferred[0].bucket == "own_reasoning"
    drifted = [row for row in ledger.rows if row.bucket == "cited_drifted"]
    assert drifted[0].text.startswith("The company also said headcount doubled")
    assert "From that we infer" not in drifted[0].text
    assert sum(ledger.counts["by_bucket"].values()) == ledger.counts["units"]
    assert {row.bucket for row in ledger.rows} <= set(BUCKETS)
    cited = [row for row in ledger.rows if row.bucket.startswith("cited")]
    assert all(row.support_status == "insufficient" for row in cited)
    assert ledger.segmenter.sha256 == LedgerSegmenter().sha256
    assert ledger.to_dict()["sha256"] == ledger.sha256


def test_ledger_refuses_an_artifact_the_run_did_not_check(tmp_path):
    artifact, execution = _run(tmp_path)
    with pytest.raises(ValueError, match="does not match the artifact"):
        build_claim_ledger(execution, artifact.read_text() + "\nExtra line.\n")


def test_ledger_refuses_a_run_with_a_different_claim_layout(tmp_path):
    artifact, execution = _run(tmp_path)
    forged = json.loads(json.dumps(execution))
    forged["execution"]["run"]["evidence"]["accounts"].pop()
    with pytest.raises(ValueError, match="no account for citation"):
        build_claim_ledger(forged, artifact.read_text())


def test_ledger_cli_writes_json_and_markdown(tmp_path):
    artifact, execution = _run(tmp_path)
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(execution))
    out = tmp_path / "ledger.json"
    md = tmp_path / "ledger.md"
    code = ledger_main(
        ["--run", str(run_path), "--artifact", str(artifact), "--out", str(out), "--markdown", str(md)]
    )
    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["schema"] == "groundnut-claim-ledger/v1"
    text = md.read_text()
    assert "Report's own reasoning" in text
    assert "$184,000" in text
    assert "not a statement that the claim is true" in text
    assert render_ledger_markdown(build_claim_ledger(execution, artifact.read_text())) == text


def test_ic_loop_replays_offline_and_writes_the_four_artifacts(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact, _ = _run(tmp_path)
    out = tmp_path / "loop"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    code = loop_main(["--report", str(artifact), "--out", str(out), "--replay-only"])
    assert code == 0
    for name in ("request.json", "run.json", "ledger.json", "ledger.md"):
        assert (out / name).exists()
    request = json.loads((out / "request.json").read_text())
    assert request["acquisition_mode"] == "replay_only"
    assert request["domain"]["key"] == "ic_research"
    ledger = json.loads((out / "ledger.json").read_text())
    assert ledger["counts"]["units"] == 6


def test_ic_loop_refuses_network_without_consent(tmp_path, monkeypatch):
    from groundnut import ic_loop

    artifact, _ = _run(tmp_path)
    out = tmp_path / "loop"
    out.mkdir()
    calls = []
    monkeypatch.setattr(
        ic_loop, "execute_request",
        lambda request, **kw: calls.append(kw) or {"schema": "groundnut-canonical-error/v1"},
    )
    code = ic_loop.main(["--report", str(artifact), "--out", str(out), "--replay-only"])
    assert code == 2
    assert calls == [{"base_directory": out, "allow_live": False}]

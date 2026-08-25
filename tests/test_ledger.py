import json
from pathlib import Path

import pytest

from groundnut.canonical_cli import execute_request
from groundnut.ledger import (
    BUCKETS,
    LedgerSegmenter,
    _accounts_by_location,
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
    assert ledger.counts["units"] == 7
    assert by_detail == {
        "excerpt_found:found": 1,
        "citation_unconfirmed:quote_not_found": 1,
        "own_reasoning:numeric": 1,
        "own_reasoning:narrative": 4,
    }
    inferred = [row for row in ledger.rows if row.text.startswith("From that we infer")]
    assert inferred and inferred[0].bucket == "own_reasoning"
    drifted = [row for row in ledger.rows if row.bucket == "citation_unconfirmed"]
    assert drifted[0].text.startswith("The company also said headcount doubled")
    assert "From that we infer" not in drifted[0].text
    assert sum(ledger.counts["by_bucket"].values()) == ledger.counts["units"]
    assert {row.bucket for row in ledger.rows} <= set(BUCKETS)
    cited = [row for row in ledger.rows if row.bucket != "own_reasoning"]
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


def test_ledger_restores_numeric_citation_order_after_canonical_sorting():
    def account(claim_id):
        return {
            "assessment": {
                "verification": {
                    "claim": {"claim_id": claim_id, "location": "line 1"}
                }
            }
        }

    accounts = [
        account(claim_id)
        for claim_id in (
            "c1", "c10", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"
        )
    ]
    indexed = _accounts_by_location({"evidence": {"accounts": accounts}})
    claim_ids = [
        indexed[("line 1", index)]["assessment"]["verification"]["claim"]["claim_id"]
        for index in range(10)
    ]

    assert claim_ids == [f"c{index}" for index in range(1, 11)]


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
    assert payload["schema"] == "groundnut-claim-ledger/v3"
    text = md.read_text()
    assert "Report's own reasoning" in text
    assert "$184,000" in text
    assert "not a statement that the claim is true" in text
    assert render_ledger_markdown(build_claim_ledger(execution, artifact.read_text())) == text


def test_ic_loop_replays_offline_and_writes_bound_artifacts(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact, _ = _run(tmp_path)
    out = tmp_path / "loop"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    code = loop_main(["--report", str(artifact), "--out", str(out), "--replay-only"])
    assert code == 0
    for name in ("request.json", "run.json", "ledger.json", "ledger.md", "gate.json"):
        assert (out / name).exists()
    request = json.loads((out / "request.json").read_text())
    assert request["acquisition_mode"] == "replay_only"
    assert request["domain"]["key"] == "ic_research"
    ledger = json.loads((out / "ledger.json").read_text())
    assert ledger["counts"]["units"] == 7


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


def test_ic_loop_preserves_complete_previous_outputs_when_a_rerun_fails(
    tmp_path, monkeypatch
):
    from groundnut import ic_loop

    artifact, _ = _run(tmp_path)
    out = tmp_path / "loop"
    out.mkdir()
    previous = {}
    for name in ("request.json", "run.json", "ledger.json", "ledger.md"):
        previous[name] = f"previous {name}\n"
        (out / name).write_text(previous[name])
    monkeypatch.setattr(
        ic_loop,
        "execute_request",
        lambda request, **kw: {"schema": "groundnut-canonical-error/v1"},
    )

    assert ic_loop.main(["--report", str(artifact), "--out", str(out), "--replay-only"]) == 2
    assert {name: (out / name).read_text() for name in previous} == previous


DECLARED_REPORT_LINE = (
    "At a $26,000 price the condition requires value above $184,000 per year. "
    "<!-- ic-own: derived from cited price and switching cost --> "
    "Separately, we think the team can reach forty people by 2028 spending $2M."
)


def test_declared_marker_binds_to_its_sentence_not_the_paragraph(tmp_path):
    artifact, execution = _run(tmp_path)
    text = artifact.read_text().replace(
        "At a $26,000 price and $20,000 of switching cost the condition requires value above $184,000 per year.",
        DECLARED_REPORT_LINE,
    )
    artifact.write_text(text)
    from groundnut.canonical_cli import execute_request as _exec  # rerun on edited artifact

    execution = _exec(
        json.loads((tmp_path / "request.json").read_text())
        if (tmp_path / "request.json").exists()
        else None,
        base_directory=tmp_path,
    ) if False else None
    # Rebuild the run against the edited artifact via the loop's own path:
    from groundnut.ic_loop import run_loop

    out = tmp_path / "declared"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    summary = run_loop(artifact, out, replay_only=True)
    ledger = json.loads((out / "ledger.json").read_text())
    own = [r for r in ledger["rows"] if r["bucket"] == "own_reasoning"]
    declared = [r for r in own if r["detail"] == "declared"]
    numeric = [r for r in own if r["detail"] == "numeric"]
    assert len(declared) == 1 and "$184,000" in declared[0]["text"]
    assert any("forty people" in r["text"] for r in numeric)
    assert summary["undeclared_numerics"] == len(numeric)


def test_gate_fails_on_undeclared_numerics_and_names_them(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact, _ = _run(tmp_path)
    out = tmp_path / "gated"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    code = loop_main(
        ["--report", str(artifact), "--out", str(out), "--replay-only", "--gate-undeclared-numerics"]
    )
    assert code == 1
    # artifacts still written for inspection
    assert (out / "ledger.md").exists()


def test_gate_passes_when_every_numeric_is_declared_or_cited(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact, _ = _run(tmp_path)
    text = artifact.read_text().replace(
        "the condition requires value above $184,000 per year.",
        "the condition requires value above $184,000 per year. <!-- ic-own -->",
    )
    artifact.write_text(text)
    out = tmp_path / "clean"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    code = loop_main(
        ["--report", str(artifact), "--out", str(out), "--replay-only", "--gate-undeclared-numerics"]
    )
    assert code == 0


def test_short_numeric_sentence_cannot_escape_the_gate(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact, _ = _run(tmp_path)
    artifact.write_text(artifact.read_text() + "\nMarket: $4.2B by 2030.\n")
    out = tmp_path / "short-numeric"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())

    code = loop_main(
        ["--report", str(artifact), "--out", str(out), "--replay-only", "--gate-undeclared-numerics"]
    )

    assert code == 1
    ledger = json.loads((out / "ledger.json").read_text())
    assert any(
        row["text"] == "Market: $4.2B by 2030." and row["detail"] == "numeric"
        for row in ledger["rows"]
    )


def test_zero_citation_report_is_a_valid_all_own_reasoning_run(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact = tmp_path / "uncited.md"
    artifact.write_text(
        "# Memo\n\nThis report contains a factual statement without any external citation.\n"
    )
    out = tmp_path / "uncited-out"

    code = loop_main(["--report", str(artifact), "--out", str(out), "--replay-only"])

    assert code == 0
    run = json.loads((out / "run.json").read_text())
    assert run["execution"]["run"]["artifact"]["claim_count"] == 0
    assert run["execution"]["run"]["evidence"]["accounts"] == []
    ledger = json.loads((out / "ledger.json").read_text())
    assert ledger["counts"]["by_bucket"] == {
        "citation_unconfirmed": 0,
        "excerpt_found": 0,
        "own_reasoning": 1,
    }


@pytest.mark.parametrize(
    ("name", "report", "anomaly"),
    [
        ("empty", "# Heading only\n", None),
        (
            "unclosed-fence",
            "# Memo\n\n```text\nMarket reaches $9B by 2031.\n",
            "unclosed_fence",
        ),
        (
            "unclosed-frontmatter",
            "---\ntitle: Memo\nMarket reaches $9B by 2031.\n",
            "unclosed_frontmatter",
        ),
    ],
)
def test_gate_never_clears_an_empty_or_malformed_population(
    tmp_path, name, report, anomaly
):
    from groundnut.ic_loop import main as loop_main

    artifact = tmp_path / f"{name}.md"
    artifact.write_text(report)
    out = tmp_path / f"{name}-out"

    code = loop_main(
        ["--report", str(artifact), "--out", str(out), "--replay-only",
         "--gate-undeclared-numerics"]
    )

    assert code == 1
    gate = json.loads((out / "gate.json").read_text())
    assert gate["status"] == "indeterminate"
    assert gate["population"]["status"] in {"empty", "malformed"}
    assert gate["population"]["units"] == 0
    if anomaly:
        assert [row["code"] for row in gate["population"]["anomalies"]] == [anomaly]


def test_markdown_table_cells_enter_the_numeric_gate(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact = tmp_path / "table.md"
    artifact.write_text(
        "# Metrics\n\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        "| TAM 2030 | $4.2B |\n"
        "| ARR exit | $88M |\n"
        "| Burn | $1.4M/mo |\n"
    )
    out = tmp_path / "table-out"

    code = loop_main(
        ["--report", str(artifact), "--out", str(out), "--replay-only",
         "--gate-undeclared-numerics"]
    )

    assert code == 1
    ledger = json.loads((out / "ledger.json").read_text())
    assert ledger["population"]["status"] == "observed"
    assert ledger["population"]["included_lines"] == {"table_row": 3}
    assert ledger["population"]["excluded_lines"]["table_header"] == 1
    assert ledger["population"]["excluded_lines"]["table_delimiter"] == 1
    assert ledger["counts"]["units"] == 6
    assert ledger["counts"]["by_detail"]["own_reasoning:numeric"] == 4


def test_table_without_outer_pipes_uses_the_same_population_contract(tmp_path):
    from groundnut.ic_loop import GateFailure, run_loop

    artifact = tmp_path / "compact-table.md"
    artifact.write_text(
        "Metric | Value\n"
        "--- | ---\n"
        "ARR exit | $88M\n"
    )
    out = tmp_path / "compact-table-out"

    with pytest.raises(GateFailure, match="undeclared numeric"):
        run_loop(artifact, out, replay_only=True, gate_undeclared_numerics=True)
    ledger = json.loads((out / "ledger.json").read_text())
    assert ledger["population"]["included_lines"] == {"table_row": 1}
    assert [row["text"] for row in ledger["rows"]] == ["ARR exit", "$88M"]


def test_citation_and_declared_analysis_are_surfaced_without_engine_policy(tmp_path):
    artifact, execution = _run(tmp_path)
    text = artifact.read_text().replace(
        "in the last filing.",
        "in the last filing. <!-- ic-own: derived from the filing -->",
    )
    artifact.write_text(text)

    from groundnut.ic_loop import run_loop

    out = tmp_path / "annotation-conflict"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    run_loop(artifact, out, replay_only=True)
    ledger = json.loads((out / "ledger.json").read_text())
    conflicting = [row for row in ledger["rows"] if row["annotation_conflicts"]]

    assert len(conflicting) == 1
    assert conflicting[0]["annotations"] == ["citation", "declared_analysis"]
    assert conflicting[0]["annotation_conflicts"] == [
        "citation_and_declared_analysis"
    ]
    assert ledger["counts"]["annotation_conflicts"] == 1
    gate = json.loads((out / "gate.json").read_text())
    assert gate["annotation_conflicts"] == [
        {"unit_id": conflicting[0]["unit_id"],
         "codes": ["citation_and_declared_analysis"]}
    ]


def test_closed_fence_is_a_named_exclusion_not_a_population_anomaly(tmp_path):
    from groundnut.ic_loop import run_loop

    artifact = tmp_path / "closed-fence.md"
    artifact.write_text(
        "# Memo\n\nOne ordinary report statement.\n\n"
        "```text\nMarket reaches $9B by 2031.\n```\n"
    )
    out = tmp_path / "closed-fence-out"
    summary = run_loop(artifact, out, replay_only=True, gate_undeclared_numerics=True)
    ledger = json.loads((out / "ledger.json").read_text())

    assert summary["gate_status"] == "clear"
    assert ledger["population"]["status"] == "observed"
    assert ledger["population"]["anomalies"] == []
    assert ledger["population"]["excluded_lines"]["fenced_code"] == 1


def test_human_waiver_must_bind_the_exact_failed_ledger(tmp_path):
    from groundnut.ic_loop import main as loop_main

    artifact, _ = _run(tmp_path)
    out = tmp_path / "waived"
    out.mkdir()
    (out / "snapshots").mkdir()
    for item in (tmp_path / "snapshots").iterdir():
        (out / "snapshots" / item.name).write_bytes(item.read_bytes())
    args = [
        "--report", str(artifact), "--out", str(out), "--replay-only",
        "--gate-undeclared-numerics",
    ]
    assert loop_main(args) == 1
    ledger = json.loads((out / "ledger.json").read_text())
    failing = [
        row["unit_id"]
        for row in ledger["rows"]
        if row["bucket"] == "own_reasoning" and row["detail"] == "numeric"
    ]
    waiver_path = tmp_path / "waiver.json"
    waiver_path.write_text(
        json.dumps(
            {
                "schema": "groundnut-gate-waiver/v1",
                "gate": "undeclared_numeric_own_reasoning",
                "artifact_sha256": ledger["artifact_sha256"],
                "ledger_sha256": ledger["sha256"],
                "approved_by": "human:reviewer",
                "approved_at": "2026-08-25T12:00:00Z",
                "reason": "Reviewed as an explicit scenario assumption.",
                "waived_unit_ids": failing,
            }
        )
    )

    assert loop_main([*args, "--waiver", str(waiver_path)]) == 0
    gate = json.loads((out / "gate.json").read_text())
    assert gate["status"] == "waived"
    assert gate["waiver"]["approved_by"] == "human:reviewer"
    assert len(gate["waiver"]["sha256"]) == 64

import pytest

from groundnut.arena_emission import ArenaEmissionProfile, emit_arena_tasks
from groundnut.provenance import sha256_text


HTML = """
<section class="slide">
  <h2>Channel</h2>
  <p>The ledger records $3.0 million paid through Distributor A.</p>
  <p>Therefore the company is likely to depend heavily on Distributor A.</p>
</section>
<section class="slide">
  <h2>Costs</h2>
  <p>Public unit counts and listed prices are the stated inputs.</p>
  <p>A bottom-up estimate puts annual operating costs at $1.7 million.</p>
</section>
<section class="slide">
  <h2>Renewal</h2>
  <p>The agreement expires in December 2026.</p>
  <p>There is no documented renewal on record for the agreement.</p>
</section>
<section class="slide">
  <p>Unrelated evidence says Distributor B renewed through 2028.</p>
</section>
"""


def test_emits_three_trigger_classes_with_section_containment(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(HTML)
    result = emit_arena_tasks(path)

    assert [task.trigger for task in result.tasks] == [
        "inferential",
        "derived",
        "absence",
    ]
    assert result.tasks[0].context == "The ledger records $3.0 million paid through Distributor A."
    assert result.tasks[1].context == "Public unit counts and listed prices are the stated inputs."
    assert "renewed through 2028" not in result.tasks[2].context
    assert result.input_sha256 == sha256_text(HTML)
    assert result.to_dict()["schema"] == "groundnut-arena-task-emission/v1"


def test_specific_triggers_take_priority_over_inferential_words(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "# Findings\n"
        "Therefore the bottom-up estimate puts annual demand at $1.7 million.\n"
        "The channel likely has no documented renewal on record.\n"
    )
    tasks = emit_arena_tasks(path).tasks
    assert tasks[0].trigger == "derived"
    assert tasks[1].trigger == "absence"


def test_deduplicates_repeated_conclusions(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "# One\nTherefore the market will double over the next five years.\n"
        "# Two\nTherefore the market will double over the next five years.\n"
    )
    assert len(emit_arena_tasks(path).tasks) == 1


def test_heading_boundaries_prevent_context_leakage(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "# Earlier\nThe earlier section records $9.0 million.\n"
        "# Finding\nThe current ledger records $3.0 million.\n"
        "Therefore the company is likely to depend heavily on this channel.\n"
    )
    [task] = emit_arena_tasks(path).tasks
    assert "$3.0 million" in task.context
    assert "$9.0 million" not in task.context


def test_profile_patterns_are_hash_bound_and_configurable(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("The evidence conclusively establishes a material dependency here.\n")
    default = ArenaEmissionProfile(key="custom", version="1")
    changed = ArenaEmissionProfile(
        key="custom",
        version="1",
        inferential_patterns=(r"\bconclusively establishes\b",),
    )
    assert default.sha256 != changed.sha256
    [task] = emit_arena_tasks(path, changed).tasks
    assert task.trigger == "inferential"


def test_plain_facts_and_meta_text_are_not_tasks(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "Prepared for Example Holdings on 17 August 2026.\n"
        "The office is located in Boston and opened during 2024.\n"
    )
    assert emit_arena_tasks(path).tasks == ()


def test_unsupported_artifact_and_invalid_profile_fail_closed(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="unsupported arena artifact suffix"):
        emit_arena_tasks(path)
    with pytest.raises(ValueError, match="character bounds"):
        ArenaEmissionProfile(key="bad", version="1", min_characters=50, max_characters=10)

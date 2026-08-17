import json

from groundnut.arena_cli import main


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def fixture_files(tmp_path, *, ruling="misses"):
    policy = tmp_path / "policy.json"
    tasks = tmp_path / "tasks.jsonl"
    attacks = tmp_path / "attacks.jsonl"
    rulings = tmp_path / "rulings.jsonl"
    output = tmp_path / "report.json"
    policy.write_text(json.dumps({
        "key": "test", "version": "1", "frozen_at": "2026-08-17T00:00:00Z",
        "lenses": ["premise"], "required_rulings": 2,
    }))
    write_jsonl(tasks, [{
        "task_id": "t1", "assertion": "claim", "context": "context", "location": "line 1",
    }])
    write_jsonl(attacks, [{
        "task_id": "t1", "lens": "premise", "attack": "challenge", "severity": "material",
        "model": "attacker", "model_family": "a", "session_id": "attack-session",
    }])
    write_jsonl(rulings, [
        {"task_id": "t1", "lens": "premise", "ruling": ruling, "reason": "r",
         "model": "judge-1", "model_family": "b", "session_id": "judge-1"},
        {"task_id": "t1", "lens": "premise", "ruling": ruling, "reason": "r",
         "model": "judge-2", "model_family": "c", "session_id": "judge-2"},
    ])
    return policy, tasks, attacks, rulings, output


def test_cli_writes_passing_report_and_returns_zero(tmp_path):
    paths = fixture_files(tmp_path)
    code = main(["--policy", str(paths[0]), "--tasks", str(paths[1]),
                 "--attacks", str(paths[2]), "--rulings", str(paths[3]),
                 "--out", str(paths[4])])

    assert code == 0
    assert json.loads(paths[4].read_text())["passed"] is True


def test_cli_returns_one_for_valid_non_passing_report(tmp_path):
    paths = fixture_files(tmp_path, ruling="lands")
    code = main(["--policy", str(paths[0]), "--tasks", str(paths[1]),
                 "--attacks", str(paths[2]), "--rulings", str(paths[3]),
                 "--out", str(paths[4])])

    assert code == 1
    assert json.loads(paths[4].read_text())["findings"][0]["verdict"] == "flagged"


def test_cli_returns_two_for_invalid_input(tmp_path):
    paths = fixture_files(tmp_path)
    paths[1].write_text("not json\n")

    assert main(["--policy", str(paths[0]), "--tasks", str(paths[1]),
                 "--attacks", str(paths[2]), "--rulings", str(paths[3]),
                 "--out", str(paths[4])]) == 2

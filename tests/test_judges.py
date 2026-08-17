"""Deterministic tests for the two gate judges (harness/judges.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from judges import grounding, high_severity_precision, norm_text  # noqa: E402


def _write_pred(d, doc_id, findings):
    (d / f"{doc_id}.json").write_text(json.dumps({"findings": findings}))


def test_norm_text_folds_quotes_dashes_whitespace():
    assert norm_text("It’s  a “Cap—On\nLiability”") == "it's a \"cap-on liability\""


def test_grounding_exact_and_reflowed_pass_fabricated_fails(tmp_path):
    pred = tmp_path / "pred"
    src = tmp_path / "contracts"
    pred.mkdir(); src.mkdir()
    (src / "d1.txt").write_text(
        'This Agreement may not be assigned\nwithout the prior written consent of Buyer.'
    )
    _write_pred(pred, "d1", {
        # exact substring
        "Anti-Assignment": ["may not be assigned\nwithout the prior"],
        # reflowed whitespace + case still grounds
        "Change Of Control": ["THIS AGREEMENT MAY NOT   BE ASSIGNED without"],
        # fabricated quote does not
        "Uncapped Liability": ["liability shall be unlimited in all respects"],
    })
    g, n, misses = grounding(pred, src)
    assert (g, n) == (2, 3)
    assert misses == [("d1", "Uncapped Liability", "liability shall be unlimited in all respects")]


def test_grounding_respects_doc_filter(tmp_path):
    pred = tmp_path / "pred"
    src = tmp_path / "contracts"
    pred.mkdir(); src.mkdir()
    (src / "d1.txt").write_text("alpha beta")
    (src / "d2.txt").write_text("gamma delta")
    _write_pred(pred, "d1", {"Parties": ["alpha"]})
    _write_pred(pred, "d2", {"Parties": ["nonsense"]})
    g, n, _ = grounding(pred, src, doc_ids={"d1"})
    assert (g, n) == (1, 1)


def test_high_severity_precision_counts_only_high_categories(tmp_path):
    pred = tmp_path / "pred"
    pred.mkdir()
    gold = {
        "d1": {"gold": {
            "Change Of Control": ["a change of control of the Company triggers consent"],
            "Governing Law": ["governed by the laws of England"],
        }},
    }
    sevmap = {"Change Of Control": 5, "Governing Law": 2, "Uncapped Liability": 5}
    _write_pred(pred, "d1", {
        # High, matches gold -> TP
        "Change Of Control": ["a change of control of the Company triggers consent"],
        # High, no gold span -> FP
        "Uncapped Liability": ["liability shall be unlimited"],
        # low severity: ignored entirely, even though wrong
        "Governing Law": ["governed by the laws of Mars"],
    })
    tp, fp = high_severity_precision(pred, gold, sevmap)
    assert (tp, fp) == (1, 1)


def test_high_severity_precision_missing_pred_file_is_no_predictions(tmp_path):
    pred = tmp_path / "pred"
    pred.mkdir()
    gold = {"d9": {"gold": {"Change Of Control": ["x y z"]}}}
    tp, fp = high_severity_precision(pred, gold, {"Change Of Control": 5})
    assert (tp, fp) == (0, 0)

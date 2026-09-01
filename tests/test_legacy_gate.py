from harness.gate import evaluate_bars


def _decisions(**overrides):
    values = {
        "macro_f1_value": 0.55,
        "grounded": 95,
        "grounding_total": 100,
        "high_tp": 7,
        "high_fp": 3,
        "probe_gap": 0.05,
    }
    values.update(overrides)
    return {name: passed for name, _, _, passed in evaluate_bars(**values)}


def test_legacy_gate_freezes_all_four_thresholds():
    assert all(_decisions().values())
    assert not _decisions(macro_f1_value=0.5499)["macro-F1"]
    assert not _decisions(grounded=9499, grounding_total=10000)["quote-grounding"]
    assert not _decisions(high_tp=6999, high_fp=3001)["High-sev precision"]
    assert not _decisions(probe_gap=0.0501)["probe gap"]


def test_legacy_gate_rejects_vacuous_or_unmeasured_populations():
    assert not _decisions(grounded=0, grounding_total=0)["quote-grounding"]
    assert not _decisions(high_tp=0, high_fp=0)["High-sev precision"]
    assert not _decisions(probe_gap=None)["probe gap"]

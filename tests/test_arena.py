import pytest

from groundnut.arena import ArenaPolicy, ArenaTask, Attack, Ruling, adjudicate


POLICY = ArenaPolicy(
    key="test_review",
    version="1",
    frozen_at="2026-08-17T00:00:00Z",
    lenses=("wrong_premise", "unsupported_leap", "alternative_explanation"),
)
TASK = ArenaTask("t1", "Therefore the market will double.", "Premises.", "line 1")


def attack(lens, text=None, session="attack-session"):
    return Attack(
        task_id="t1",
        lens=lens,
        attack=text,
        severity="material" if text else None,
        model="attacker",
        model_family="family-a",
        session_id=session,
    )


def rulings(lens, first="lands", second="lands"):
    return [
        Ruling("t1", lens, first, "reason", "judge-1", "family-b", "judge-1"),
        Ruling("t1", lens, second, "reason", "judge-2", "family-c", "judge-2"),
    ]


def complete_attacks(challenged_lens="unsupported_leap"):
    return [
        attack(
            lens,
            "The conclusion exceeds the premise." if lens == challenged_lens else None,
        )
        for lens in POLICY.lenses
    ]


def test_two_family_consensus_flags_attack():
    report = adjudicate(
        POLICY,
        [TASK],
        complete_attacks(),
        rulings("unsupported_leap"),
    )

    assert report.findings[0].verdict == "flagged"
    assert report.passed is False
    assert report.policy_sha256 == POLICY.sha256


def test_disagreement_is_withheld_not_exonerated():
    report = adjudicate(
        POLICY,
        [TASK],
        complete_attacks(),
        rulings("unsupported_leap", "lands", "misses"),
    )

    assert report.findings[0].verdict == "withheld"
    assert report.withheld_density == 1.0
    assert report.passed is False


def test_missing_lens_or_ruling_fails_closed():
    missing_lens = adjudicate(POLICY, [TASK], [attack("wrong_premise")], [])
    incomplete_ruling = adjudicate(
        POLICY,
        [TASK],
        complete_attacks(),
        rulings("unsupported_leap")[:1],
    )

    assert missing_lens.findings[0].verdict == "unruled"
    assert incomplete_ruling.findings[0].verdict == "unruled"


def test_attacker_cannot_rule_its_own_attack():
    bad = Ruling(
        "t1",
        "unsupported_leap",
        "lands",
        "reason",
        "same",
        "family-z",
        "attack-session",
    )
    with pytest.raises(ValueError, match="own attack"):
        adjudicate(POLICY, [TASK], complete_attacks(), [bad])

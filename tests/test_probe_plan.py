import pytest

from groundnut.probe_plan import SupportProbePlan


def plan():
    return SupportProbePlan(
        key="legal-support-pilot-v1",
        frozen_at="2026-08-17T00:00:00Z",
        group_count=50,
        sampling_seed=991,
        probe_sha256="c" * 64,
        source_pool_sha256="a" * 64,
        excluded_pool_sha256="b" * 64,
        max_context_characters=4096,
        primary_metric="macro_f1",
        minimum_improvement=0.05,
        baseline_policy_keys=("exact-v1",),
        detector_policy_keys=("lettuce-v2", "minicheck"),
        lexical_overlap_min=0.2,
        lexical_overlap_max=0.8,
    )


def test_plan_is_order_stable_and_freezes_sample_size():
    first = plan()
    second = SupportProbePlan(
        **{
            **first.__dict__,
            "baseline_policy_keys": tuple(reversed(first.baseline_policy_keys)),
            "detector_policy_keys": tuple(reversed(first.detector_policy_keys)),
        }
    )
    assert first.sha256 == second.sha256
    with pytest.raises(ValueError, match="group count differs"):
        first.validate_probe(first.probe_sha256, 49)


def test_plan_requires_a_positive_preregistered_difference():
    with pytest.raises(ValueError, match="minimum improvement"):
        SupportProbePlan(**{**plan().__dict__, "minimum_improvement": 0})

import math

import pytest

from groundnut.signals import (
    ComponentLicence,
    ComponentSignal,
    SignalBundle,
    component_input_sha256,
)
from groundnut.support import DetectorIdentity


IDENTITY = DetectorIdentity(
    adapter="groundnut.test.v1",
    model="test-model",
    revision="0123456789abcdef",
    package="test-package",
    package_version="1.0.0",
)
LICENCE = ComponentLicence(
    code_spdx="MIT",
    code_source="https://example.test/code",
    model_spdx="Apache-2.0",
    model_source="https://example.test/model",
)
INPUT_SHA = component_input_sha256(
    source_text="The source.",
    claim_text="The claim.",
    question="The question?",
)


def signal(role="entailment", score=0.75):
    return ComponentSignal(
        role=role,
        label="supported",
        scores={"score": score},
        input_sha256=INPUT_SHA,
        component=IDENTITY,
        licence=LICENCE,
        raw_output={"score": score, "labels": ["supported"]},
        note="One component observation; not a truth claim.",
    )


def test_component_signal_preserves_raw_output_and_replays_hashes():
    first = signal()
    second = signal()

    assert first.to_dict()["raw_output"] == {
        "score": 0.75,
        "labels": ["supported"],
    }
    assert first.raw_output_sha256 == second.raw_output_sha256
    assert first.sha256 == second.sha256
    assert first.to_dict()["licence"]["code_spdx"] == "MIT"


def test_signal_bundle_sorts_without_collapsing_independent_signals():
    bundle = SignalBundle(
        claim_id="claim-1",
        input_sha256=INPUT_SHA,
        signals=(signal("unsupported", 0.2), signal("entailment", 0.8)),
    )

    assert [row.role for row in bundle.signals] == ["entailment", "unsupported"]
    assert len(bundle.to_dict()["signals"]) == 2
    assert len(bundle.sha256) == 64


def test_signal_bundle_rejects_mixed_inputs_and_duplicate_organs():
    wrong = ComponentSignal(
        role="relevance",
        label="irrelevant",
        scores={"score": 0.1},
        input_sha256="a" * 64,
        component=IDENTITY,
        licence=LICENCE,
        raw_output={"score": 0.1},
        note="Different input.",
    )
    with pytest.raises(ValueError, match="different component input"):
        SignalBundle("claim-1", INPUT_SHA, (signal(), wrong))
    with pytest.raises(ValueError, match="repeats"):
        SignalBundle("claim-1", INPUT_SHA, (signal(), signal()))


def test_component_signal_rejects_unknown_roles_bad_scores_and_non_json():
    with pytest.raises(ValueError, match="unknown component signal role"):
        signal("oracle")
    with pytest.raises(ValueError, match="between 0 and 1"):
        signal(score=1.1)
    with pytest.raises(ValueError, match="finite JSON"):
        ComponentSignal(
            role="entailment",
            label="supported",
            scores={"score": 0.5},
            input_sha256=INPUT_SHA,
            component=IDENTITY,
            licence=LICENCE,
            raw_output={"score": math.nan},
            note="Invalid raw output.",
        )


def test_component_licence_requires_model_fields_as_a_pair():
    with pytest.raises(ValueError, match="must appear together"):
        ComponentLicence(
            code_spdx="MIT",
            code_source="https://example.test/code",
            model_spdx="MIT",
        )

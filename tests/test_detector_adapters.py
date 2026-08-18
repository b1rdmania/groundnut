import pytest

from groundnut.adapters import (
    AlignScoreAdapter,
    LettuceDetectAdapter,
    MiniCheckAdapter,
    SummaCAdapter,
)
from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
from groundnut.support import SupportPolicy, assess_claim_support
from groundnut.verification import Claim, verify_claim


SOURCE = "Revenue was $14.2M."
CLAIM = "Revenue was $14.2M."
REFERENCE = SourceReference("s1", "memory://s1")


def resolution():
    return SourceResolution(
        source=ResolvedSource(
            reference=REFERENCE,
            text=SOURCE,
            fetched_at="2026-08-17T00:00:00Z",
            media_type="text/plain",
        )
    )


def checked(detector, threshold=None, question=None):
    claim = Claim("c1", CLAIM, source=REFERENCE, question=question)
    mechanical = verify_claim(claim, resolution())
    policy = SupportPolicy(
        key="adapter-test",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=detector.identity,
        min_confidence=threshold,
    )
    return assess_claim_support(
        mechanical,
        resolution(),
        detector=detector,
        policy=policy,
    )


class FakeLettuce:
    def __init__(self, spans):
        self.spans = spans
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return self.spans


def lettuce(spans, threshold=0.5):
    backend = FakeLettuce(spans)
    adapter = LettuceDetectAdapter(
        model="KRLabsOrg/lettucedect-v2-mmbert-base",
        revision="0123456789abcdef",
        span_threshold=threshold,
        backend=backend,
        installed_package_version="0.2.2",
    )
    return adapter, backend


def test_lettuce_clean_output_is_unscored_support_under_explicit_policy():
    adapter, backend = lettuce([])
    result = checked(adapter, threshold=None, question="What was revenue?")

    assert result.support.status == "supported"
    assert result.support.decision.confidence is None
    assert backend.calls[0]["question"] == "What was revenue?"
    assert backend.calls[0]["min_confidence"] == 0.5
    assert len(result.support.decision.raw_output_sha256) == 64


def test_lettuce_only_maps_explicit_typed_contradiction_to_contradicted():
    adapter, _ = lettuce([
        {
            "start": 12,
            "end": 18,
            "text": "$14.2M",
            "confidence": 0.93,
            "category": "contradiction",
            "subcategory": "numerical",
        }
    ])
    result = checked(adapter, threshold=0.8)

    assert result.support.status == "contradicted"
    assert result.support.decision.spans[0].label == "contradiction/numerical"


def test_lettuce_untyped_unsupported_span_is_insufficient_not_contradicted():
    adapter, _ = lettuce([
        {"start": 12, "end": 18, "text": "$14.2M", "confidence": 0.91}
    ])
    result = checked(adapter, threshold=0.8)

    assert result.support.status == "insufficient"
    assert result.support.decision.spans[0].label == "unsupported"


def test_lettuce_configuration_hash_pins_threshold():
    first, _ = lettuce([], threshold=0.5)
    second, _ = lettuce([], threshold=0.8)

    assert first.identity.configuration_sha256 != second.identity.configuration_sha256
    assert first.identity.sha256 != second.identity.sha256


class FakeMiniCheck:
    def __init__(self, label, probability):
        self.label = label
        self.probability = probability
        self.calls = []

    def score(self, **kwargs):
        self.calls.append(kwargs)
        return [self.label], [self.probability], None, None


def minicheck(label, probability):
    scorer = FakeMiniCheck(label, probability)
    adapter = MiniCheckAdapter(
        scorer=scorer,
        model="flan-t5-large",
        revision="abcdef0123456789",
        installed_package_version="1.0.0",
    )
    return adapter, scorer


def test_minicheck_supported_mapping_records_probability_and_inputs():
    adapter, scorer = minicheck(1, 0.94)
    result = checked(adapter, threshold=0.8)

    assert result.support.status == "supported"
    assert result.support.decision.confidence == 0.94
    assert scorer.calls == [{"docs": [SOURCE], "claims": [CLAIM]}]


def test_minicheck_negative_is_insufficient_never_contradicted():
    adapter, _ = minicheck(0, 0.08)
    result = checked(adapter, threshold=0.8)

    assert result.support.status == "insufficient"
    assert result.support.decision.confidence == 0.92
    assert "cannot distinguish contradiction" in result.support.decision.reason


def test_adapter_errors_fail_closed_through_support_contract():
    adapter, _ = minicheck(7, 1.5)
    result = checked(adapter, threshold=0.8)

    assert result.support.status == "not_assessed"
    assert result.support.failure == "detector_error:ValueError"


def test_minicheck_requires_preloaded_pinned_scorer():
    with pytest.raises(ValueError, match="pinned scorer"):
        MiniCheckAdapter(
            scorer=None,
            model="flan-t5-large",
            revision="abcdef0123456789",
            installed_package_version="1.0.0",
        )


class FakeAlignScore:
    def __init__(self, probabilities):
        self.probabilities = probabilities
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "probabilities": self.probabilities,
            "selected_chunk_sha256": "a" * 64,
        }


def alignscore(mode, probabilities):
    backend = FakeAlignScore(probabilities)
    adapter = AlignScoreAdapter(
        mode=mode,
        model="yzha/AlignScore-base",
        revision="8509e78d25bb914939fc585c626500c9b2944249",
        backend=backend,
        installed_package_version="0.1.3+a0936d5afee6",
    )
    return adapter, backend


def test_alignscore_nli_preserves_contradiction_instead_of_collapsing_score():
    adapter, backend = alignscore("nli", [0.02, 0.08, 0.90])
    result = checked(adapter, question="What was revenue?")

    assert result.support.status == "contradicted"
    assert result.support.decision.confidence == 0.90
    assert backend.calls[0]["mode"] == "nli"


def test_alignscore_qa_requires_and_passes_the_claim_question():
    adapter, backend = alignscore("qa", [0.85, 0.15])
    result = checked(adapter, question="What was revenue?")

    assert result.support.status == "insufficient"
    assert backend.calls[0]["question"] == "What was revenue?"


def test_alignscore_qa_without_question_fails_closed():
    adapter, _ = alignscore("qa", [0.1, 0.9])
    result = checked(adapter)

    assert result.support.status == "not_assessed"
    assert result.support.failure == "detector_error:ValueError"


class FakeSummaC:
    def __init__(self, score, image=None):
        self.score = score
        self.image = image
        self.calls = []

    def score_one(self, **kwargs):
        self.calls.append(kwargs)
        if self.image is None:
            return self.score
        return {"score": self.score, "image": self.image}


def summac(score, threshold=0.0):
    scorer = FakeSummaC(score)
    adapter = SummaCAdapter(
        scorer=scorer,
        model="summac-zs-vitc",
        revision="abcdef0123456789",
        installed_package_version="0.0.4",
        model_licence_spdx="Apache-2.0",
        model_source="https://example.test/summac-zs-vitc",
        threshold=threshold,
    )
    return adapter, scorer


def test_summac_preserves_raw_signal_before_binary_support_mapping():
    adapter, scorer = summac(0.62)
    scorer.image = [[[0.81]], [[0.19]], [[0.0]]]

    signal = adapter.assess_signal(
        source_text=SOURCE,
        claim_text=CLAIM,
        question="What was revenue?",
    )
    result = checked(adapter, question="What was revenue?")

    assert signal.role == "entailment"
    assert signal.label == "supported"
    assert signal.raw_output["raw_consistency_score"] == 0.62
    assert signal.raw_output["normalized_consistency_score"] == 0.81
    assert signal.raw_output["published_output"]["image"] == scorer.image
    assert signal.raw_output["question_used"] is False
    assert signal.licence.code_spdx == "Apache-2.0"
    assert result.support.status == "supported"
    assert result.support.decision.raw_output_sha256 == signal.raw_output_sha256
    assert scorer.calls[0] == {"original": SOURCE, "generated": CLAIM}


def test_summac_negative_is_insufficient_and_never_types_contradiction():
    adapter, _ = summac(-0.6)
    result = checked(adapter, question="What was revenue?")

    assert result.support.status == "insufficient"
    assert result.support.decision.confidence == 0.8
    assert "cannot distinguish contradiction" in result.support.decision.reason
    assert "question relevance" in result.support.decision.reason


def test_summac_threshold_is_part_of_component_identity():
    first, _ = summac(0.6, threshold=0.0)
    second, _ = summac(0.6, threshold=0.2)

    assert first.identity.configuration_sha256 != second.identity.configuration_sha256


def test_summac_requires_injected_scorer_and_fails_closed_on_bad_output():
    with pytest.raises(ValueError, match="pinned scorer"):
        SummaCAdapter(
            scorer=None,
            model="summac-zs-vitc",
            revision="abcdef0123456789",
            installed_package_version="0.0.4",
            model_licence_spdx="Apache-2.0",
            model_source="https://example.test/summac-zs-vitc",
        )

    adapter, _ = summac(1.2)
    result = checked(adapter)
    assert result.support.status == "not_assessed"
    assert result.support.failure == "detector_error:ValueError"

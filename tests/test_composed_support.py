from dataclasses import dataclass

from groundnut.composed_support import ExactThenFallbackSupportDetector
from groundnut.support import DetectorDecision, DetectorIdentity, SupportPolicy


@dataclass
class StubFallback:
    decision: DetectorDecision

    identity = DetectorIdentity(
        adapter="test.semantic",
        model="frozen-test-model",
        revision="abc123",
        package="test-package",
        package_version="1",
    )

    def __post_init__(self):
        self.calls = 0

    def assess(self, *, source_text, claim_text, question):
        self.calls += 1
        return self.decision


def test_exact_positive_never_reaches_the_fallback():
    fallback = StubFallback(
        DetectorDecision("contradicted", 0.9, "Fallback says contradicted.")
    )
    detector = ExactThenFallbackSupportDetector(fallback)

    result = detector.assess(
        source_text="The supplier shall deliver in thirty days.",
        claim_text="The supplier shall deliver in thirty days.",
        question=None,
    )

    assert result.label == "supported"
    assert fallback.calls == 0


def test_exact_miss_preserves_the_fallback_label_and_confidence():
    fallback = StubFallback(
        DetectorDecision("contradicted", 0.73, "Pinned NLI selected contradiction.")
    )
    detector = ExactThenFallbackSupportDetector(fallback)

    result = detector.assess(
        source_text="The supplier shall deliver in thirty days.",
        claim_text="The supplier may deliver whenever it chooses.",
        question="When must delivery occur?",
    )

    assert result.label == "contradicted"
    assert result.confidence == 0.73
    assert result.reason.startswith("Exact-first route missed;")
    assert fallback.calls == 1


def test_identity_binds_the_fallback_identity_and_routing_rule():
    first = ExactThenFallbackSupportDetector.identity_for(StubFallback.identity)
    changed = DetectorIdentity(
        **{
            **StubFallback.identity.__dict__,
            "revision": "def456",
        }
    )
    second = ExactThenFallbackSupportDetector.identity_for(changed)

    assert first.adapter == "groundnut.composed.exact_then_fallback.v1"
    assert first.configuration_sha256 != second.configuration_sha256


def test_frozen_candidate_policy_binds_the_explored_fallback():
    policy = SupportPolicy.from_json("policies/composed-support-candidate-v1.json")
    fallback = DetectorIdentity(
        adapter="groundnut.alignscore.nli.v1",
        model="yzha/AlignScore-base",
        revision="8509e78d25bb914939fc585c626500c9b2944249",
        package="alignscore",
        package_version="0.1.3+a0936d5afee6",
        configuration_sha256=(
            "4c0036860fef981cdee84336fe41f1a08906e37ca36d3df09bc91df6c6a6cd2c"
        ),
    )

    assert policy.detector == ExactThenFallbackSupportDetector.identity_for(fallback)
    assert policy.min_confidence == 0.5
    assert policy.sha256 == (
        "1e0b4705bc3c8ff57d161b8c95ac4e4f37bb34012156bbd09a0a6c9fbe6a318b"
    )

import json

import pytest

from groundnut.provenance import sha256_text
from groundnut.sources import ResolvedSource, SourceReference, SourceResolution
from groundnut.support import ExactSupportDetector, SupportPolicy, assess_claim_support
from groundnut.support_cases import CASE_KINDS, SupportCase, SupportProbe
from groundnut.support_eval import score_support
from groundnut.verification import Claim, verify_claim


SOURCE = (
    "Introduction. "
    "The supplier shall deliver the audited report within thirty days. "
    "Boilerplate. The agreement is governed by English law. "
    "Closing text that makes the document long enough for a narrow window."
)
ORIGINAL = "The supplier shall deliver the audited report within thirty days."
START = SOURCE.index(ORIGINAL)
QUESTION = "What is the supplier's delivery obligation?"


CLAIMS = {
    "verbatim_supported": ORIGINAL,
    "paraphrase_supported": "The supplier must provide an audited report within 30 days.",
    "contradicted": "The supplier is not required to deliver an audited report.",
    "present_irrelevant": "The agreement is governed by English law.",
}


def case(kind, *, group="g1", question=QUESTION, start=START):
    original = SOURCE[start : start + len(ORIGINAL)]
    return SupportCase(
        case_id=f"{group}-{kind}",
        group_id=group,
        kind=kind,
        expected_status=CASE_KINDS[kind],
        source_id="source-1",
        source_sha256=sha256_text(SOURCE),
        original_start=start,
        original_end=start + len(ORIGINAL),
        original_text=original,
        question=question,
        claim_text=CLAIMS[kind],
    )


def probe():
    return SupportProbe(tuple(case(kind) for kind in CASE_KINDS))


def test_probe_requires_all_four_cells_and_shared_origin():
    with pytest.raises(ValueError, match="exactly four kinds"):
        SupportProbe((case("verbatim_supported"),))

    rows = [case(kind) for kind in CASE_KINDS]
    rows[-1] = case("present_irrelevant", question="A different task")
    with pytest.raises(ValueError, match="one source span and question"):
        SupportProbe(tuple(rows))


def test_source_validation_makes_substring_baseline_non_trivial():
    current = probe()
    current.validate_sources({"source-1": SOURCE})

    present = {row.kind: row.claim_text in SOURCE for row in current.cases}
    assert present == {
        "verbatim_supported": True,
        "paraphrase_supported": False,
        "contradicted": False,
        "present_irrelevant": True,
    }


def test_source_validation_rejects_circular_or_tampered_cases():
    bad_paraphrase = case("paraphrase_supported")
    bad_paraphrase = SupportCase(
        **{
            **bad_paraphrase.canonical_payload(),
            "claim_text": ORIGINAL,
        }
    )
    with pytest.raises(ValueError, match="must be absent"):
        bad_paraphrase.validate_source(SOURCE)

    with pytest.raises(ValueError, match="source hash mismatch"):
        case("contradicted").validate_source(SOURCE + " changed")


def test_every_group_member_receives_identical_context_window():
    contexts = probe().contexts({"source-1": SOURCE}, max_characters=100)

    assert len(set(contexts.values())) == 1
    assert ORIGINAL in next(iter(contexts.values()))


def test_manifest_hash_is_order_independent_and_gold_keeps_kinds():
    first = probe()
    second = SupportProbe(tuple(reversed(first.cases)))

    assert first.sha256 == second.sha256
    assert {row.kind for row in first.gold()} == set(CASE_KINDS)


def test_exact_baseline_cannot_solve_the_four_cell_probe():
    current = probe()
    reference = SourceReference("source-1", "memory://source-1")
    resolution = SourceResolution(
        source=ResolvedSource(
            reference=reference,
            text=SOURCE,
            fetched_at="2026-08-17T00:00:00Z",
            media_type="text/plain",
        )
    )
    detector = ExactSupportDetector()
    policy = SupportPolicy(
        key="exact",
        version="1",
        frozen_at="2026-08-17T00:00:00Z",
        detector=detector.identity,
        min_confidence=1.0,
    )
    predictions = []
    for row in current.cases:
        claim = Claim(
            row.case_id,
            row.claim_text,
            source=reference,
            question=row.question,
        )
        predictions.append(
            assess_claim_support(
                verify_claim(claim, resolution),
                resolution,
                detector=detector,
                policy=policy,
            ).support
        )

    score = score_support(current.gold(), predictions)

    assert score["accuracy"] == 0.25


def test_jsonl_loader_reports_line_and_preserves_manifest(tmp_path):
    path = tmp_path / "cases.jsonl"
    current = probe()
    path.write_text(
        "".join(json.dumps(row.canonical_payload()) + "\n" for row in current.cases)
    )

    loaded = SupportProbe.from_jsonl(path)

    assert loaded.sha256 == current.sha256
    path.write_text("{}\n")
    with pytest.raises(ValueError, match=r"cases.jsonl:1"):
        SupportProbe.from_jsonl(path)

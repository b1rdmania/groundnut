import csv
import io
import json

import pytest

from groundnut.provenance import sha256_text
from groundnut.support_review import (
    PilotReviewManifest,
    PilotReviewRow,
    apply_review_decisions_tsv,
    build_pilot_probe,
    prepare_review_manifest,
    propose_negation_flip,
    review_decisions_tsv,
)
from groundnut.support_review_html import render_support_review_html
from groundnut.support_cases import CaseProvenance
from groundnut.support_seeds import AttestedSpanSeed, PresentIrrelevantCandidate


SOURCE = (
    "Opening. The supplier shall deliver the audited report within thirty days. "
    "The agreement is governed by English law. Closing."
)
ORIGINAL = "The supplier shall deliver the audited report within thirty days."
DISTRACTOR = "The agreement is governed by English law."
START = SOURCE.index(ORIGINAL)
DISTRACTOR_START = SOURCE.index(DISTRACTOR)


def seed():
    return AttestedSpanSeed(
        seed_id="seed-1",
        source_id="doc.txt",
        source_sha256=sha256_text(SOURCE),
        original_start=START,
        original_end=START + len(ORIGINAL),
        original_text=ORIGINAL,
        question="What is the supplier's delivery obligation?",
        provenance=CaseProvenance(
            kind="attested",
            source="legalbenchrag",
            source_record_id="cuad:1",
            method="expert span; generated query",
        ),
    )


def candidate():
    return PresentIrrelevantCandidate(
        candidate_id="candidate-1",
        target_seed_id="seed-1",
        distractor_seed_id="seed-2",
        source_id="doc.txt",
        source_sha256=sha256_text(SOURCE),
        original_start=START,
        original_end=START + len(ORIGINAL),
        original_text=ORIGINAL,
        distractor_start=DISTRACTOR_START,
        distractor_end=DISTRACTOR_START + len(DISTRACTOR),
        question="What is the supplier's delivery obligation?",
        claim_text=DISTRACTOR,
    )


def manifest():
    return prepare_review_manifest(
        (candidate(),),
        {"doc.txt": SOURCE},
        target_group_count=1,
        reserve_count=0,
        sampling_seed=991,
        max_context_characters=len(SOURCE),
        source_pool_sha256="a" * 64,
        excluded_pool_sha256="b" * 64,
        lexical_overlap_min=0.2,
        lexical_overlap_max=0.8,
    )


def completed_rows():
    current = manifest()
    text = review_decisions_tsv(current.rows)
    reader = csv.DictReader(io.StringIO(text), dialect="excel-tab")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, dialect="excel-tab")
    writer.writeheader()
    for row in reader:
        row.update(
            {
                "irrelevant_decision": "accepted",
                "irrelevant_reviewer_id": "human:r1",
                "paraphrase_text": "An audited report must be provided within thirty days.",
                "paraphrase_author_kind": "agent",
                "paraphrase_author_id": "model:pinned",
                "paraphrase_decision": "accepted",
                "paraphrase_reviewer_id": "human:r1",
                "contradiction_decision": "accepted",
                "contradiction_reviewer_id": "human:r1",
            }
        )
        writer.writerow(row)
    return current, apply_review_decisions_tsv(current.rows, output.getvalue())


def test_review_manifest_freezes_context_order_and_negation_proposal():
    current = manifest()
    row = current.rows[0]

    assert ORIGINAL in row.context_text
    assert DISTRACTOR in row.context_text
    assert "shall not deliver" in row.contradiction_text
    assert len(current.sha256) == 64
    restored = PilotReviewManifest.from_mapping(current.to_dict(), current.rows)
    assert restored.sha256 == current.sha256


def test_review_tsv_rejects_immutable_display_tampering():
    current = manifest()
    text = review_decisions_tsv(current.rows).replace(DISTRACTOR, "Changed text")

    with pytest.raises(ValueError, match="changed present_candidate_text"):
        apply_review_decisions_tsv(current.rows, text)


def test_completed_review_builds_a_valid_balanced_probe():
    current, rows = completed_rows()
    reviewed_manifest = PilotReviewManifest.from_mapping(current.to_dict(), rows)
    probe = build_pilot_probe(
        reviewed_manifest,
        (seed(),),
        {"doc.txt": SOURCE},
    )

    assert probe.group_count == 1
    assert len(probe.cases) == 4
    assert {row.kind for row in probe.cases} == {
        "verbatim_supported",
        "paraphrase_supported",
        "contradicted",
        "present_irrelevant",
    }
    contexts = probe.contexts({"doc.txt": SOURCE}, len(SOURCE))
    assert len(set(contexts.values())) == 1


def test_pending_review_cannot_be_promoted():
    current = manifest()

    with pytest.raises(ValueError, match="review is pending"):
        build_pilot_probe(current, (seed(),), {"doc.txt": SOURCE})


def test_review_row_rejects_rehashed_candidate_context_tampering():
    row = manifest().rows[0]
    value = json.loads(json.dumps(row.canonical_payload()))
    value["context"]["text"] += "tampered"
    value["context"]["end"] += len("tampered")
    value["context"]["sha256"] = sha256_text(value["context"]["text"])

    with pytest.raises(ValueError, match="immutable input hash mismatch"):
        PilotReviewRow.from_mapping(value)


def test_negation_flip_is_deterministic_and_refuses_unhandled_text():
    assert propose_negation_flip("Supplier must not disclose.")[0] == (
        "Supplier must disclose."
    )
    assert propose_negation_flip("A defined noun phrase.") is None


def test_offline_reviewer_embeds_only_the_frozen_private_batch():
    current = manifest()
    html = render_support_review_html(current)

    assert current.sha256 in html
    assert ORIGINAL in html
    assert "default-src 'none'" in html
    assert "https://" not in html
    assert "Download reviewed TSV" in html

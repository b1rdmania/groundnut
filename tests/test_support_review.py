import dataclasses
import csv
import io
import json

import pytest

from groundnut.provenance import sha256_text
from groundnut.support_review import (
    build_pilot_probe_with_receipt,
    PilotReviewManifest,
    PilotReviewRow,
    apply_review_decisions_tsv,
    build_pilot_probe,
    prepare_review_manifest,
    propose_negation_flip,
    review_decisions_tsv,
)
from groundnut.support_review_html import render_support_review_html
from groundnut.support_agent_screen import AgentSuggestion, screen_agent_suggestions
from groundnut.support import ExactSupportDetector
from groundnut.support_exploration import (
    compare_agent_explorations,
    run_agent_exploration,
)
from groundnut.support_cases import CaseProvenance
from groundnut.support_seeds import AttestedSpanSeed, PresentIrrelevantCandidate
from groundnut.adapters import SummaCAdapter


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


def completed_rows(current=None, overrides=None, per_row=None):
    current = current or manifest()
    text = review_decisions_tsv(current.rows)
    reader = csv.DictReader(io.StringIO(text), dialect="excel-tab")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, dialect="excel-tab")
    writer.writeheader()
    for index, row in enumerate(reader):
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
                **(overrides or {}),
                **((per_row or {}).get(index, {})),
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


@pytest.mark.parametrize(
    "overrides",
    [
        {"irrelevant_reviewer_id": "agent:gpt-x"},
        {"paraphrase_reviewer_id": "agent:gpt-x"},
        {"contradiction_reviewer_id": "agent:gpt-x"},
        {"paraphrase_reviewer_id": "human:"},
        {"paraphrase_author_id": "human:r1", "paraphrase_author_kind": "agent"},
    ],
)
def test_accepted_decisions_require_a_separate_human_reviewer(overrides):
    with pytest.raises(ValueError, match="human: reviewer|cannot be its author"):
        completed_rows(overrides=overrides)


def test_human_may_author_and_accept_their_own_paraphrase():
    _, rows = completed_rows(
        overrides={"paraphrase_author_id": "human:r1", "paraphrase_author_kind": "human"}
    )
    assert all(row.ready for row in rows)


def test_reserve_replacement_is_recorded_in_the_build_receipt():
    second = dataclasses.replace(
        candidate(), candidate_id="candidate-2", target_seed_id="seed-b", source_id="other.txt"
    )
    second_seed = dataclasses.replace(seed(), seed_id="seed-b", source_id="other.txt")
    sources = {"doc.txt": SOURCE, "other.txt": SOURCE}
    current = prepare_review_manifest(
        (candidate(), second),
        sources,
        target_group_count=1,
        reserve_count=1,
        sampling_seed=991,
        max_context_characters=len(SOURCE),
        source_pool_sha256="a" * 64,
        excluded_pool_sha256="b" * 64,
        lexical_overlap_min=0.2,
        lexical_overlap_max=0.8,
    )
    first_rejected = {
        index: {"irrelevant_decision": "rejected"}
        for index, row in enumerate(current.rows)
        if row.candidate.candidate_id == current.rows[0].candidate.candidate_id
    }
    current, rows = completed_rows(current, per_row=first_rejected)
    reviewed = PilotReviewManifest.from_mapping(current.to_dict(), rows)
    probe, receipt = build_pilot_probe_with_receipt(
        reviewed, (seed(), second_seed), sources, build_attempt=2
    )

    assert probe.group_count == 1
    assert receipt.to_dict() == {
        "schema": "groundnut-support-probe-build/v2",
        "probe_sha256": probe.sha256,
        "review_manifest_sha256": reviewed.sha256,
        "build_attempt": 2,
        "rows_walked": 2,
        "selected": 1,
        "rejected": 1,
        "ambiguous": 0,
    }


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


def test_offline_reviewer_keeps_agent_draft_separate_from_human_decision():
    current = manifest()
    row = current.rows[0]
    suggestion = {
        "schema": "groundnut-support-agent-suggestion/v1",
        "input_sha256": row.input_sha256,
        "agent": "local:test-model",
        "irrelevant_decision": "accepted",
        "irrelevant_note": "Different clause.",
        "paraphrase_text": "A distinct supported restatement.",
        "paraphrase_note": "Meaning retained.",
        "paraphrase_lexical_overlap": 0.4,
        "paraphrase_absent_from_context": True,
        "contradiction_decision": "accepted",
        "contradiction_note": "Polarity reversed.",
        "requires_human_review": True,
    }
    html = render_support_review_html(
        current, {row.input_sha256: suggestion}
    )

    assert "local:test-model" in html
    assert "review, do not rubber-stamp" in html
    assert 'irrelevant_decision: row.irrelevance_review.decision' in html


def agent_suggestion(**updates):
    row = manifest().rows[0]
    values = {
        "input_sha256": row.input_sha256,
        "agent": "local:test-model",
        "irrelevant_decision": "accepted",
        "irrelevant_note": "The candidate addresses a different obligation.",
        "paraphrase_text": "An audited report is due within thirty days.",
        "paraphrase_note": "The duty and deadline are retained.",
        "paraphrase_lexical_overlap": 0.4,
        "paraphrase_absent_from_context": True,
        "contradiction_decision": "accepted",
        "contradiction_note": "The proposed mutation reverses the duty.",
        "requires_human_review": True,
    }
    values.update(updates)
    return AgentSuggestion(**values)


def test_agent_screen_is_exploratory_and_structurally_ineligible():
    current = manifest()
    screen = screen_agent_suggestions(current, (agent_suggestion(),))

    artifact = screen.to_dict()
    assert artifact["qualification"] == "exploratory_only"
    assert artifact["eligible_for_admission"] is False
    assert artifact["included_group_count"] == 1
    assert artifact["included_case_count"] == 4
    assert len(artifact["sha256"]) == 64


def test_agent_screen_excludes_disagreement_instead_of_resolving_it():
    screen = screen_agent_suggestions(
        manifest(),
        (agent_suggestion(contradiction_decision="ambiguous"),),
    )

    assert screen.included_input_sha256 == ()
    assert screen.excluded[0][1] == ("contradiction_ambiguous",)


def test_agent_suggestion_boolean_strings_are_rejected():
    value = {
        "schema": "groundnut-support-agent-suggestion/v1",
        **agent_suggestion().__dict__,
        "requires_human_review": "true",
    }

    with pytest.raises(ValueError, match="flags must be booleans"):
        AgentSuggestion.from_mapping(value)


def test_agent_exploration_runs_without_creating_an_admission_result():
    result = run_agent_exploration(
        manifest(), (agent_suggestion(),), ExactSupportDetector()
    )

    assert result["qualification"] == "exploratory_only"
    assert result["eligible_for_admission"] is False
    assert result["group_count"] == 1
    assert result["case_count"] == 4
    assert result["score"]["accuracy"] == 0.25
    assert result["score"]["by_kind"]["verbatim_supported"]["accuracy"] == 1.0
    assert result["score"]["by_kind"]["paraphrase_supported"]["accuracy"] == 0.0
    assert result["score"]["by_kind"]["contradicted"]["accuracy"] == 0.0
    assert result["score"]["by_kind"]["present_irrelevant"]["accuracy"] == 0.0


def test_agent_exploration_preserves_component_signal_raw_output():
    class Scorer:
        def score_one(self, **kwargs):
            return {"score": 0.4, "image": [[[0.7]], [[0.3]], [[0.0]]]}

    detector = SummaCAdapter(
        scorer=Scorer(),
        model="summac-test",
        revision="abcdef0123456789",
        installed_package_version="0.0.4",
        model_licence_spdx="MIT",
        model_source="https://example.test/model",
    )
    result = run_agent_exploration(manifest(), (agent_suggestion(),), detector)

    assert all("component_signal" in row for row in result["rows"])
    first = result["rows"][0]["component_signal"]
    assert first["raw_output"]["published_output"]["image"] == [
        [[0.7]],
        [[0.3]],
        [[0.0]],
    ]
    assert first["raw_output_sha256"] == result["rows"][0]["decision"][
        "raw_output_sha256"
    ]


def test_agent_exploration_comparison_preserves_non_admission_boundary():
    run = run_agent_exploration(
        manifest(), (agent_suggestion(),), ExactSupportDetector()
    )
    comparison = compare_agent_explorations({"first": run, "second": run})

    assert comparison["eligible_for_admission"] is False
    assert comparison["case_count"] == 4
    assert comparison["results"]["first"]["binary_accuracy"] == 0.5
    assert comparison["results"]["first"]["unsupported_recall"] == 0.5

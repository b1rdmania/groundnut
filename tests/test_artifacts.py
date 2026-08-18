import json

import pytest

from groundnut.artifacts import ArtifactProfile, SegmenterIdentity, extract_artifact
from groundnut.provenance import sha256_text


def test_structured_json_maps_claims_and_binds_profile_and_input(tmp_path):
    path = tmp_path / "claims.json"
    path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "revenue",
                        "claim_text": "Revenue was $4.2 million in 2025.",
                        "verification_question": "What was revenue in 2025?",
                        "source_url": "https://example.test/filing",
                        "source_excerpt": "Revenue for 2025 was $4.2 million.",
                    },
                    {
                        "claim_text": "Costs are estimated at $1.7 million.",
                        "source_url": None,
                        "source_excerpt": None,
                        "declared_analysis": True,
                        "provenance_class": "analyst_calculation",
                        "calculation": {
                            "formula": "cost = licences * price_per_licence",
                            "inputs": [
                                {
                                    "name": "licences",
                                    "value": "10",
                                    "source_claim_ids": ["revenue"],
                                },
                                {
                                    "name": "price_per_licence",
                                    "value": "$170,000",
                                },
                            ],
                            "note": "Illustrative reconstruction.",
                        },
                    },
                ]
            }
        )
    )
    result = extract_artifact(path)

    assert result.kind == "structured_json"
    assert result.input_sha256 == sha256_text(path.read_text())
    assert result.claims[0].claim_id == "revenue"
    assert result.claims[0].source.uri == "https://example.test/filing"
    assert result.claims[0].question == "What was revenue in 2025?"
    assert result.claims[0].location == "claims[0]"
    assert result.claims[1].declared_analysis is True
    assert result.claims[1].provenance_class == "analyst_calculation"
    assert result.claims[1].to_dict()["analytical_provenance"] == {
        "schema": "groundnut-analytical-provenance/v1",
        "class": "analyst_calculation",
        "calculation_lineage_status": "declared",
        "calculation_lineage": {
            "schema": "groundnut-calculation-lineage/v1",
            "formula": "cost = licences * price_per_licence",
            "formula_sha256": sha256_text(
                "cost = licences * price_per_licence"
            ),
            "inputs": [
                {
                    "name": "licences",
                    "value": "10",
                    "source_claim_ids": ["revenue"],
                },
                {
                    "name": "price_per_licence",
                    "value": "$170,000",
                    "source_claim_ids": [],
                },
            ],
            "note": "Illustrative reconstruction.",
        },
    }
    assert result.to_dict()["schema"] == "groundnut-artifact-extraction/v2"
    assert result.to_dict()["claim_count"] == 2
    assert result.to_dict()["segmenter"]["key"] == "groundnut.artifact-block-segmenter"


def test_profile_ports_a_structured_contract_without_product_code(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps({"assertions": [{"text": "A claim.", "url": "https://example.test/a", "intent": "What does the source establish?"}]}))
    profile = ArtifactProfile(
        key="custom",
        version="1",
        claims_key="assertions",
        claim_text_key="text",
        question_key="intent",
        source_uri_key="url",
    )
    [claim] = extract_artifact(path, profile).claims
    assert claim.text == "A claim."
    assert claim.source.uri == "https://example.test/a"
    assert claim.question == "What does the source establish?"
    assert claim.location == "assertions[0]"


def test_markdown_preserves_adjacent_quote_and_locator(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "Revenue was $4.2m in 2025 [filing](https://example.test/a)"
        "<!-- groundnut-source-quote: Revenue was exactly $4.2m. -->"
        "<!-- groundnut-verification-question: What was revenue in 2025? -->\n"
        "The licence is active [registry](https://example.test/b)"
        "<!-- groundnut-source-locator: table: licence status -->\n"
    )
    result = extract_artifact(path)
    assert result.claims[0].excerpt == "Revenue was exactly $4.2m."
    assert result.claims[0].locator is None
    assert result.claims[0].question == "What was revenue in 2025?"
    assert result.claims[1].excerpt is None
    assert result.claims[1].locator == "table: licence status"


def test_empty_verification_question_comment_is_ignored(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "A claim [source](https://example.test/a)"
        "<!-- groundnut-verification-question: -->\n"
    )
    [claim] = extract_artifact(path).claims
    assert claim.question is None


def test_html_recovers_evidence_and_declared_analysis_but_ignores_references(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(
        '<section><p>Revenue was $4.2m in 2025 <a href="https://example.test/a">filing</a>'
        '<!-- groundnut-source-quote: Revenue was "exactly" $4.2m. -->'
        '<!-- groundnut-verification-question: What was revenue in 2025? --></p>'
        '<p>Costs are a $1.7m estimate <span class="groundnut-declared-analysis">analyst reconstruction</span></p></section>'
        '<ol class="groundnut-references"><li><a href="https://example.test/a">source list only</a></li></ol>'
    )
    result = extract_artifact(path)
    assert len(result.claims) == 2
    assert result.claims[0].excerpt == 'Revenue was "exactly" $4.2m.'
    assert result.claims[0].question == "What was revenue in 2025?"
    assert result.claims[1].source is None
    assert result.claims[1].declared_analysis is True
    assert result.claims[1].provenance_class == "analyst_inference"
    assert "source list only" not in str(result.to_dict())


def test_title_quote_and_locator_convention_remain_distinct(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(
        '<p><a href="https://example.test/a" title="Source: filing | quote: Revenue was &quot;up&quot; 40%">Revenue rose</a>.</p>'
        '<p><a href="https://example.test/b" title="quote: [table: Item 5]">Revenue table</a>.</p>'
    )
    first, second = extract_artifact(path).claims
    assert first.excerpt == 'Revenue was "up" 40%'
    assert second.excerpt is None
    assert second.locator == "table: Item 5"


def test_invalid_artifacts_fail_closed(tmp_path):
    missing = tmp_path / "missing.json"
    missing.write_text("{}")
    with pytest.raises(ValueError, match="claims array"):
        extract_artifact(missing)

    wrong_boolean = tmp_path / "wrong-boolean.json"
    wrong_boolean.write_text(
        json.dumps({"claims": [{"claim_text": "Claim", "declared_analysis": "yes"}]})
    )
    with pytest.raises(ValueError, match="must be boolean"):
        extract_artifact(wrong_boolean)

    unsupported = tmp_path / "claims.txt"
    unsupported.write_text("claim")
    with pytest.raises(ValueError, match="unsupported artifact suffix"):
        extract_artifact(unsupported)


def test_profile_hash_changes_with_parser_contract():
    default = ArtifactProfile(key="profile", version="1")
    changed = ArtifactProfile(
        key="profile", version="1", evidence_comment_prefix="other-source"
    )
    assert default.sha256 != changed.sha256

    changed_question_marker = ArtifactProfile(
        key="profile", version="1", question_comment_marker="ic-verification-question"
    )
    assert default.sha256 != changed_question_marker.sha256

    changed_segmenter = ArtifactProfile(
        key="profile",
        version="1",
        segmenter=SegmenterIdentity(
            key="groundnut.artifact-block-segmenter",
            version="2",
            strategies=(("structured_json", "one claim per row"),),
        ),
    )
    assert default.sha256 != changed_segmenter.sha256

    changed_exclusions = ArtifactProfile(
        key="profile",
        version="1",
        ignored_container_attributes=("data-host-evidence-exclude",),
    )
    assert default.sha256 != changed_exclusions.sha256


def test_profile_ports_custom_citation_and_question_comments(tmp_path):
    path = tmp_path / "ic-report.md"
    path.write_text(
        "Revenue increased [filing](https://example.test/a)"
        "<!-- ic-source-quote: Revenue increased by 20%. -->"
        "<!-- ic-verification-question: How much did revenue increase? -->\n"
    )
    profile = ArtifactProfile(
        key="ic-report",
        version="1",
        evidence_comment_prefix="ic-source",
        question_comment_marker="ic-verification-question",
    )
    [claim] = extract_artifact(path, profile).claims
    assert claim.excerpt == "Revenue increased by 20%."
    assert claim.question == "How much did revenue increase?"


def test_html_ignores_only_profile_declared_attribute_regions(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(
        '<nav data-groundnut-evidence-exclude><a href="https://example.test/chrome">Chrome</a></nav>'
        '<p>Claim <a href="https://example.test/evidence">Evidence</a></p>'
    )
    [claim] = extract_artifact(path).claims
    assert claim.source.uri == "https://example.test/evidence"


def test_typed_html_provenance_is_preserved_without_becoming_support(tmp_path):
    path = tmp_path / "typed.html"
    path.write_text(
        '<p><span class="groundnut-company-assertion">The company reports six pilots.</span></p>'
        '<p><span class="groundnut-analyst-calculation">Modelled ARR is £140,000.</span></p>'
        '<p><span class="groundnut-open-question">What is current ARR?</span></p>'
    )
    claims = extract_artifact(path).claims
    assert [claim.provenance_class for claim in claims] == [
        "company_assertion",
        "analyst_calculation",
        "open_question",
    ]
    assert claims[0].declared_analysis is False
    assert claims[1].declared_analysis is True
    assert claims[2].declared_analysis is False


def test_conflicting_provenance_fails_closed(tmp_path):
    path = tmp_path / "conflict.html"
    path.write_text(
        '<p class="groundnut-company-assertion groundnut-recommendation">Claim</p>'
    )
    with pytest.raises(ValueError, match="conflicting provenance"):
        extract_artifact(path)

    path.write_text(
        '<p class="groundnut-company-assertion groundnut-declared-analysis">Claim</p>'
    )
    with pytest.raises(ValueError, match="legacy declared-analysis"):
        extract_artifact(path)


def test_profile_rejects_non_object_provenance_markers():
    with pytest.raises(ValueError, match="provenance_class_markers must be an object"):
        ArtifactProfile.from_mapping(
            {
                "key": "bad",
                "version": "1",
                "html": {"provenance_class_markers": ["not", "a", "mapping"]},
            }
        )


def test_calculation_lineage_fails_closed_on_wrong_class_or_reference(tmp_path):
    path = tmp_path / "bad-calculation.json"
    calculation = {
        "formula": "result = input",
        "inputs": [
            {"name": "input", "value": "1", "source_claim_ids": ["missing"]}
        ],
    }
    path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "result",
                        "claim_text": "Result is one.",
                        "provenance_class": "analyst_calculation",
                        "calculation": calculation,
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="unknown claims"):
        extract_artifact(path)

    calculation["inputs"][0]["source_claim_ids"] = []
    path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "result",
                        "claim_text": "Result is one.",
                        "provenance_class": "recommendation",
                        "calculation": calculation,
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="requires analyst_calculation"):
        extract_artifact(path)

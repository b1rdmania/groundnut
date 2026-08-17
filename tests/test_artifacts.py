import json

import pytest

from groundnut.artifacts import ArtifactProfile, extract_artifact
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
                        "source_url": "https://example.test/filing",
                        "source_excerpt": "Revenue for 2025 was $4.2 million.",
                    },
                    {
                        "claim_text": "Costs are estimated at $1.7 million.",
                        "source_url": None,
                        "source_excerpt": None,
                        "declared_analysis": True,
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
    assert result.claims[0].location == "claims[0]"
    assert result.claims[1].declared_analysis is True
    assert result.to_dict()["schema"] == "groundnut-artifact-extraction/v1"


def test_profile_ports_a_structured_contract_without_product_code(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps({"assertions": [{"text": "A claim.", "url": "https://example.test/a"}]}))
    profile = ArtifactProfile(
        key="custom",
        version="1",
        claims_key="assertions",
        claim_text_key="text",
        source_uri_key="url",
    )
    [claim] = extract_artifact(path, profile).claims
    assert claim.text == "A claim."
    assert claim.source.uri == "https://example.test/a"
    assert claim.location == "assertions[0]"


def test_markdown_preserves_adjacent_quote_and_locator(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(
        "Revenue was $4.2m in 2025 [filing](https://example.test/a)"
        "<!-- groundnut-source-quote: Revenue was exactly $4.2m. -->\n"
        "The licence is active [registry](https://example.test/b)"
        "<!-- groundnut-source-locator: table: licence status -->\n"
    )
    result = extract_artifact(path)
    assert result.claims[0].excerpt == "Revenue was exactly $4.2m."
    assert result.claims[0].locator is None
    assert result.claims[1].excerpt is None
    assert result.claims[1].locator == "table: licence status"


def test_html_recovers_evidence_and_declared_analysis_but_ignores_references(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(
        '<section><p>Revenue was $4.2m in 2025 <a href="https://example.test/a">filing</a>'
        '<!-- groundnut-source-quote: Revenue was "exactly" $4.2m. --></p>'
        '<p>Costs are a $1.7m estimate <span class="groundnut-declared-analysis">analyst reconstruction</span></p></section>'
        '<ol class="groundnut-references"><li><a href="https://example.test/a">source list only</a></li></ol>'
    )
    result = extract_artifact(path)
    assert len(result.claims) == 2
    assert result.claims[0].excerpt == 'Revenue was "exactly" $4.2m.'
    assert result.claims[1].source is None
    assert result.claims[1].declared_analysis is True
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

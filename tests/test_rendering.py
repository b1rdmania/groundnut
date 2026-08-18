import pytest

from groundnut.rendering import RendererIdentity, compare_rendered_artifacts


def test_render_receipt_binds_bytes_profiles_renderer_and_evidence_sequence(tmp_path):
    source = tmp_path / "report.md"
    source.write_text(
        "Revenue rose [filing](https://example.test/a)"
        "<!-- groundnut-source-quote: Revenue rose 10%. -->\n"
        "Licence status [registry](https://example.test/b)"
        "<!-- groundnut-source-locator: table 2 -->\n"
    )
    rendered = tmp_path / "report.html"
    rendered.write_text(
        '<nav data-groundnut-evidence-exclude><a href="https://example.test/chrome">Help</a></nav>'
        '<p>Revenue rose <a href="https://example.test/a">filing</a>'
        '<!-- groundnut-source-quote: Revenue rose 10%. --></p>'
        '<p>Licence status <a href="https://example.test/b">registry</a>'
        '<!-- groundnut-source-locator: table 2 --></p>'
    )
    renderer = RendererIdentity("fixture", "1", {"template": "reader"})

    receipt = compare_rendered_artifacts(
        source, rendered, renderer=renderer
    ).to_dict()

    assert receipt["schema"] == "groundnut-render-receipt/v1"
    assert receipt["parity"]["evidence_sequence_identical"] is True
    assert receipt["parity"]["cited_occurrences"] == 2
    assert len(receipt["parity"]["evidence_sequence_sha256"]) == 64
    assert receipt["source"]["claim_count"] == 2
    assert receipt["rendered"]["claim_count"] == 2
    assert receipt["renderer"]["configuration_sha256"] == renderer.configuration_sha256
    assert len(receipt["sha256"]) == 64


def test_render_receipt_fails_when_annotation_is_lost_or_order_changes(tmp_path):
    source = tmp_path / "report.md"
    source.write_text(
        "Claim [one](https://example.test/a)"
        "<!-- groundnut-source-quote: exact one -->\n"
        "Claim [two](https://example.test/b)"
        "<!-- groundnut-source-locator: table two -->\n"
    )
    rendered = tmp_path / "report.html"
    rendered.write_text(
        '<p>Claim <a href="https://example.test/b">two</a>'
        '<!-- groundnut-source-locator: table two --></p>'
        '<p>Claim <a href="https://example.test/a">one</a></p>'
    )

    with pytest.raises(ValueError, match="first difference at position 1"):
        compare_rendered_artifacts(
            source,
            rendered,
            renderer=RendererIdentity("broken", "1", {}),
        )


def test_renderer_identity_rejects_non_json_configuration():
    with pytest.raises(ValueError, match="canonical JSON"):
        RendererIdentity("renderer", "1", {"bad": object()})


def test_renderer_identity_snapshots_mutable_configuration():
    configuration = {"template": {"name": "reader"}}
    identity = RendererIdentity("renderer", "1", configuration)
    original_hash = identity.configuration_sha256
    configuration["template"]["name"] = "changed"

    assert identity.configuration_sha256 == original_hash
    assert identity.to_dict()["configuration"] == {"template": {"name": "reader"}}

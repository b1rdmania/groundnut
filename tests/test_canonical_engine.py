import json
from pathlib import Path

import pytest

from groundnut.domain import Category, DocumentType, DomainEvidence, DomainPack
from groundnut.engine import analyse_text
from groundnut.provenance import anchor_quote


def pack(**overrides):
    values = {
        "key": "trust_review",
        "version": "1.0.0",
        "name": "Trust review",
        "document_noun": "document",
        "extract_context": "Review this trust instrument for configured obligations.",
        "classify_context": "Classify this trust-administration document.",
        "categories": (
            Category(
                "mandatory_distribution",
                "Mandatory Distribution",
                5,
                "A distribution the trustee must make.",
            ),
        ),
        "document_types": (
            DocumentType("trust_instrument", "Trust Instrument"),
        ),
        "evidence": DomainEvidence(
            status="experimental",
            disclosure="Configuration is demonstrated; extraction quality is untested.",
        ),
    }
    values.update(overrides)
    return DomainPack(**values)


class RecordingBackend:
    name = "recording"
    model = "deterministic"

    def __init__(self):
        self.prompts = []

    def complete(self, prompt, doc_id=None):
        self.prompts.append(prompt)
        return json.dumps(
            {
                "findings": {
                    "Mandatory Distribution": [
                        "The Trustee shall distribute the income annually."
                    ]
                }
            }
        )


def test_domain_pack_hash_is_stable_and_evidence_is_explicit(tmp_path):
    original = pack()
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(original.canonical_payload(), indent=2))
    loaded = DomainPack.from_json(path)

    assert loaded == original
    assert loaded.playbook_sha256 == original.playbook_sha256
    assert loaded.manifest_sha256 == original.manifest_sha256
    assert loaded.evidence.status == "experimental"

    changed_evidence = pack(
        evidence=DomainEvidence(
            status="development",
            dataset="private-dev-v1",
            disclosure="Measured on a labelled development set; no holdout pass.",
        )
    )
    assert changed_evidence.playbook_sha256 == original.playbook_sha256
    assert changed_evidence.manifest_sha256 != original.manifest_sha256


def test_domain_pack_rejects_duplicate_category_names():
    categories = (
        Category("first", "Same", 1),
        Category("second", "Same", 2),
    )
    with pytest.raises(ValueError, match="duplicate category names"):
        pack(categories=categories)


def test_anchor_keeps_exact_and_normalised_grounding_separate():
    source = "The Trustee shall distribute\nthe income annually."
    exact = anchor_quote("trust-1", source, "The Trustee shall")
    tolerant = anchor_quote(
        "trust-1", source, "THE TRUSTEE SHALL DISTRIBUTE the income annually."
    )

    assert exact.exact is True
    assert exact.offsets == ((0, 17),)
    assert tolerant.exact is False
    assert tolerant.normalised is True
    assert tolerant.offsets == ()


def test_domain_pack_drives_prompt_and_returns_source_anchors():
    source = "The Trustee shall distribute the income annually."
    backend = RecordingBackend()
    result = analyse_text(
        source, source_id="trust-1", domain=pack(), backend=backend
    )

    assert "Review this trust instrument" in backend.prompts[0]
    assert "Mandatory Distribution: A distribution" in backend.prompts[0]
    assert "DOCUMENT TEXT:" in backend.prompts[0]
    assert result.domain_key == "trust_review"
    assert result.evidence_status == "experimental"
    assert result.findings == {"Mandatory Distribution": [source]}
    assert result.anchored_findings[0].anchor.exact is True
    assert result.anchored_findings[0].anchor.offsets == ((0, len(source)),)
    assert result.source.sha256 == result.anchored_findings[0].anchor.source_sha256

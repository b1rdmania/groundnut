import json

import pytest

from groundnut.annotations import AnnotationBundle, EvidenceAnnotation
from groundnut.provenance import sha256_text
from groundnut.support_seeds import import_legalbenchrag, load_support_seeds


def write_legalbench_fixture(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    safe = "Opening. The supplier shall deliver within thirty days. Closing."
    holdout = "Protected holdout contract text."
    (corpus / "safe.txt").write_text(safe)
    (corpus / "holdout.txt").write_text(holdout)
    start = safe.index("The supplier")
    end = safe.index(" Closing")
    benchmark = tmp_path / "cuad.json"
    benchmark.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "query": "What is the delivery obligation?",
                        "snippets": [{"file_path": "safe.txt", "span": [start, end]}],
                    },
                    {
                        "query": "What protected term applies?",
                        "snippets": [
                            {"file_path": "holdout.txt", "span": [0, len(holdout)]}
                        ],
                    },
                ]
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contracts": {
                    "h1": {
                        "split": "holdout",
                        "sha256_raw": sha256_text(holdout),
                    },
                    "d1": {"split": "dev", "sha256_raw": sha256_text(safe)},
                }
            }
        )
    )
    return corpus, benchmark, manifest, safe


def test_legalbench_import_preserves_offsets_and_excludes_holdout_by_hash(tmp_path):
    corpus, benchmark, manifest, safe = write_legalbench_fixture(tmp_path)

    result = import_legalbenchrag(
        benchmark,
        corpus,
        groundnut_manifest=manifest,
        dataset_name="cuad",
        expected_safe_sources=1,
        expected_excluded_sources=1,
    )

    assert len(result.seeds) == 1
    assert result.excluded_holdout_sources == ("holdout.txt",)
    assert result.safe_source_count == 1
    seed = result.seeds[0]
    seed.validate_source(safe)
    assert seed.provenance.kind == "attested"
    assert "generated" in seed.provenance.method
    assert seed.to_verbatim_case(group_id="g1").claim_text == seed.original_text
    assert len(result.source_pool_sha256) == 64
    assert len(result.excluded_pool_sha256) == 64
    assert len(result.manifest()["sha256"]) == 64

    output = tmp_path / "seeds.jsonl"
    output.write_text(json.dumps(seed.canonical_payload()) + "\n")
    assert load_support_seeds(output) == result.seeds


def test_legalbench_import_rejects_unsafe_paths_and_bad_offsets(tmp_path):
    corpus, benchmark, manifest, _ = write_legalbench_fixture(tmp_path)
    value = json.loads(benchmark.read_text())
    value["tests"][0]["snippets"][0]["file_path"] = "../escape.txt"
    benchmark.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="escapes corpus root"):
        import_legalbenchrag(benchmark, corpus, groundnut_manifest=manifest)


def test_legalbench_import_fails_closed_on_unexpected_inventory(tmp_path):
    corpus, benchmark, manifest, _ = write_legalbench_fixture(tmp_path)
    with pytest.raises(ValueError, match="safe source count"):
        import_legalbenchrag(
            benchmark,
            corpus,
            groundnut_manifest=manifest,
            expected_safe_sources=270,
        )


def test_annotation_interchange_requires_review_before_promotion():
    source = "A clause that supports the question."
    annotation = EvidenceAnnotation(
        annotation_id="a1",
        source_id="doc-1",
        source_sha256=sha256_text(source),
        start=0,
        end=len(source),
        text=source,
        label="supporting_span",
        question="What supports the question?",
        creator_kind="agent",
        creator_id="opencontracts-agent-1",
        review_state="accepted",
        reviewer_ids=("human:reviewer-1",),
    )
    bundle = AnnotationBundle((annotation,))
    restored = AnnotationBundle.from_jsonl(bundle.to_jsonl())

    assert restored.sha256 == bundle.sha256
    restored.annotations[0].validate_source(source)
    assert restored.annotations[0].to_attested_seed().provenance.reviewed_by == (
        "human:reviewer-1",
    )

    with pytest.raises(ValueError, match="human reviewer"):
        EvidenceAnnotation(
            **{
                **annotation.__dict__,
                "reviewer_ids": (),
            }
        )

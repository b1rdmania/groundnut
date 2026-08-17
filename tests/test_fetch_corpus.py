import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_corpus.py"
_SPEC = importlib.util.spec_from_file_location("groundnut_fetch_corpus", _SCRIPT)
assert _SPEC and _SPEC.loader
fetch_corpus = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch_corpus)


def _write_inputs(tmp_path, text):
    source = tmp_path / "CUADv1.json"
    source.write_text(
        json.dumps(
            {
                "data": [
                    {"title": "Example", "paragraphs": [{"context": text}]}
                ]
            }
        )
    )
    manifest = tmp_path / "eval" / "CORPUS-MANIFEST.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "contracts": {
                    "doc1": {
                        "cuad_title": "Example",
                        "sha256_raw": fetch_corpus.digest("canonical text"),
                        "split": "dev",
                    }
                }
            }
        )
    )
    return source, manifest


def test_fetch_corpus_enforces_manifest_hash(tmp_path, monkeypatch):
    source, manifest = _write_inputs(tmp_path, "canonical text")
    monkeypatch.setattr(fetch_corpus, "REPO", tmp_path)
    monkeypatch.setattr(fetch_corpus, "MANIFEST", manifest)
    monkeypatch.setattr(sys, "argv", ["fetch_corpus.py", "--cuad", str(source)])

    assert fetch_corpus.main() == 0
    assert (tmp_path / "eval/dev/contracts/doc1.txt").read_text() == "canonical text"


def test_fetch_corpus_rejects_same_title_with_changed_text(tmp_path, monkeypatch):
    source, manifest = _write_inputs(tmp_path, "changed text")
    monkeypatch.setattr(fetch_corpus, "REPO", tmp_path)
    monkeypatch.setattr(fetch_corpus, "MANIFEST", manifest)
    monkeypatch.setattr(sys, "argv", ["fetch_corpus.py", "--cuad", str(source)])

    assert fetch_corpus.main() == 1
    assert not (tmp_path / "eval/dev/contracts/doc1.txt").exists()

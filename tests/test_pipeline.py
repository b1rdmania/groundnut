import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pipeline.chunking as chunking_mod
from pipeline.chunking import chunk_text
from pipeline.run import load_categories, process_contract
from pipeline.backends.stub import StubBackend

FIXTURE_TEXT = (
    "SOFTWARE LICENSE AGREEMENT\n\n"
    "This Agreement is entered into between Alpha Corp (\"Alpha\") and "
    "Beta Holdings LLC (\"Beta\").\n\n"
    "1. TERM\nThis Agreement shall commence on January 1, 2020 and continue "
    "for five years.\n\n"
    "2. GOVERNING LAW\nThis Agreement shall be governed by the laws of the "
    "State of Delaware.\n"
)


def write_fixture(tmp_path, name="fixture", text=FIXTURE_TEXT):
    d = tmp_path / "contracts"
    d.mkdir(exist_ok=True)
    p = d / (name + ".txt")
    p.write_text(text)
    return p


def test_round_trip_shape(tmp_path):
    p = write_fixture(tmp_path)
    categories = load_categories()
    findings = process_contract(p, categories, StubBackend())
    assert isinstance(findings, dict)
    for cat, spans in findings.items():
        assert isinstance(cat, str)
        assert isinstance(spans, list)
        for s in spans:
            assert isinstance(s, str)


def test_verbatim_rule(tmp_path):
    p = write_fixture(tmp_path)
    categories = load_categories()
    findings = process_contract(p, categories, StubBackend())
    text = p.read_text()
    for spans in findings.values():
        for s in spans:
            assert s in text


def test_empty_or_absent_categories(tmp_path):
    p = write_fixture(tmp_path)
    categories = load_categories()
    findings = process_contract(p, categories, StubBackend())
    for cat in categories:
        # never present as null or non-list prose; absence just means omitted
        if cat in findings:
            assert isinstance(findings[cat], list)
    assert "Warranty Duration" not in findings


def test_chunking_merges_without_duplication(tmp_path, monkeypatch):
    monkeypatch.setattr(chunking_mod, "CHUNK_CHARS", 200)
    monkeypatch.setattr(chunking_mod, "OVERLAP_CHARS", 50)
    long_text = (FIXTURE_TEXT + "\n") * 5
    p = write_fixture(tmp_path, name="long", text=long_text)

    chunks = chunk_text(long_text)
    assert len(chunks) > 1

    categories = load_categories()
    findings = process_contract(p, categories, StubBackend())
    parties = findings.get("Parties", [])
    assert parties.count('Alpha Corp ("Alpha")') <= 1


def test_usage_logging(tmp_path, monkeypatch):
    usage_path = tmp_path / "usage.jsonl"
    import pipeline.backends.base as base_mod
    monkeypatch.setattr(base_mod, "USAGE_LOG", usage_path)

    p = write_fixture(tmp_path)
    categories = load_categories()
    process_contract(p, categories, StubBackend())

    assert usage_path.exists()
    lines = usage_path.read_text().strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    for key in ("backend", "model", "in_tokens", "out_tokens", "doc"):
        assert key in rec


def test_backend_swap_shape_identical(tmp_path, monkeypatch):
    p = write_fixture(tmp_path)
    categories = load_categories()
    stub_findings = process_contract(p, categories, StubBackend())

    import pipeline.backends.openai_compat as oc_mod

    class FakeResp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=120):
        content = json.dumps({"findings": {"Parties": ['Alpha Corp ("Alpha")']}})
        body = json.dumps({
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }).encode("utf-8")
        return FakeResp(body)

    monkeypatch.setenv("DD_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(oc_mod.urllib.request, "urlopen", fake_urlopen)
    oc_backend = oc_mod.OpenAICompatBackend()
    oc_findings = process_contract(p, categories, oc_backend)

    assert set(stub_findings.keys()) == set(oc_findings.keys())
    for cat in stub_findings:
        assert isinstance(oc_findings[cat], list)
        assert all(isinstance(s, str) for s in oc_findings[cat])

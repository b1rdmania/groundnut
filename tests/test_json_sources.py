"""JSON sources: json-leaf-text/v1 extraction, capture admission and replay.

Every body here is a synthetic fixture shaped like a public life-science API
record (ClinicalTrials.gov v2, bioRxiv details, Europe PMC search). Transport
is injected; no test opens a socket.
"""

import json

import pytest

import groundnut.capture as capture_module
import groundnut.sources as source_module
from groundnut.capture import (
    CaptureDeclaration,
    ReadTimeCaptureProducer,
    execute_request,
    resolve_snapshot,
    validate_capture_receipt,
)
from groundnut.sources import (
    HttpResolver,
    JsonLeafTextError,
    SnapshotFirstResolver,
    SnapshotStore,
    SourceReference,
    json_to_leaf_text,
)
from groundnut.verification import Claim, verify_claim


STUDY = (
    b'{"protocolSection":{'
    b'"identificationModule":{"nctId":"NCT99999999",'
    b'"briefTitle":"Synthetic fixture study of an investigational vaccine in adults"},'
    b'"statusModule":{"overallStatus":"COMPLETED","startDateStruct":{"date":"2020-04-29"}},'
    b'"designModule":{"phases":["PHASE2","PHASE3"],'
    b'"enrollmentInfo":{"count":47079,"type":"ACTUAL"}},'
    b'"descriptionModule":{"briefSummary":"First sentence.\\nSecond sentence.\\r\\nThird."}},'
    b'"resultsSection":{"outcomeMeasuresModule":{"outcomeMeasures":[{'
    b'"title":"Geometric mean titer","paramValue":243.40,"pValue":1e-7}]}},'
    b'"derivedSection":{"conditionBrowseModule":{"meshes":[]}},'
    b'"documentSection":{},'
    b'"hasResults":true,"withdrawnReason":null,'
    b'"sponsor":"Caf\\u00e9 Research S\\u00e3o Paulo \\"Synthetic\\""}'
)
STUDY_TEXT = "\n".join(
    [
        "protocolSection.identificationModule.nctId: NCT99999999",
        "protocolSection.identificationModule.briefTitle: "
        "Synthetic fixture study of an investigational vaccine in adults",
        "protocolSection.statusModule.overallStatus: COMPLETED",
        "protocolSection.statusModule.startDateStruct.date: 2020-04-29",
        "protocolSection.designModule.phases[0]: PHASE2",
        "protocolSection.designModule.phases[1]: PHASE3",
        "protocolSection.designModule.enrollmentInfo.count: 47079",
        "protocolSection.designModule.enrollmentInfo.type: ACTUAL",
        "protocolSection.descriptionModule.briefSummary: "
        "First sentence. Second sentence. Third.",
        "resultsSection.outcomeMeasuresModule.outcomeMeasures[0].title: "
        "Geometric mean titer",
        "resultsSection.outcomeMeasuresModule.outcomeMeasures[0].paramValue: 243.40",
        "resultsSection.outcomeMeasuresModule.outcomeMeasures[0].pValue: 1e-7",
        "derivedSection.conditionBrowseModule.meshes: []",
        "documentSection: {}",
        "hasResults: true",
        "withdrawnReason: null",
        'sponsor: Café Research São Paulo "Synthetic"',
    ]
)
EUROPE_PMC = (
    b'{"version":"6.9","hitCount":1,'
    b'"request":{"queryString":"EXT_ID:00000000","resultType":"core"},'
    b'"resultList":{"result":[{"id":"00000000","source":"MED",'
    b'"title":"Synthetic fixture article on vaccine efficacy",'
    b'"authorString":"Doe J, Roe R.","pubYear":"2020",'
    b'"journalInfo":{"volume":"383","issue":"27"},'
    b'"abstractText":"Efficacy was 95.0% (95% CI, 90.3 to 97.6).\\nNo new safety signal."}]}}'
)
STUDY_URI = "https://clinicaltrials.example.test/api/v2/studies/NCT99999999"
EUROPE_PMC_URI = (
    "https://europepmc.example.test/europepmc/webservices/rest/search"
    "?query=EXT_ID%3A00000000&resultType=core&format=json"
)


class _Headers:
    def __init__(self, media_type, values=None):
        self.media_type = media_type
        self.values = values or {}

    def get_content_type(self):
        return self.media_type

    def get(self, name, default=None):
        return self.values.get(name, default)


class _Response:
    status = 200

    def __init__(self, body, media_type, final_uri):
        self.body = body
        self.headers = _Headers(media_type)
        self.final_uri = final_uri

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def geturl(self):
        return self.final_uri

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Opener:
    """Injected transport serving fixed bodies and recording requested URIs."""

    def __init__(self, bodies, media_type="application/json"):
        self.bodies = bodies
        self.media_type = media_type
        self.requested = []

    def __call__(self, request, timeout):
        self.requested.append(request.full_url)
        body = self.bodies[request.full_url]
        return _Response(body, self.media_type, request.full_url)


def _resolver(opener, **kwargs):
    return HttpResolver(
        opener=opener,
        address_resolver=lambda hostname, port: ("93.184.216.34",),
        allow_injected_transport=True,
        **kwargs,
    )


def _resolve(body, uri=STUDY_URI, media_type="application/json", **kwargs):
    return _resolver(_Opener({uri: body}, media_type), **kwargs).resolve(
        SourceReference("fixture", uri)
    )


def _json_declaration(*extra):
    return CaptureDeclaration("public_api", ("application/json", *extra))


# --- json-leaf-text/v1 rendering -------------------------------------------


def test_json_leaf_text_renders_every_leaf_in_document_order():
    text, truncated = json_to_leaf_text(STUDY.decode())

    assert text == STUDY_TEXT
    assert truncated is False
    assert len(text.splitlines()) == len(text.split("\n")) == 17


def test_json_leaf_text_keeps_number_literals_exactly_as_written():
    text, _ = json_to_leaf_text(
        '{"a":243.40,"b":1e-7,"c":-0,"d":1E+07,"e":0.10,'
        '"f":123456789012345678901234567890}'
    )

    assert text.splitlines() == [
        "a: 243.40",
        "b: 1e-7",
        "c: -0",
        "d: 1E+07",
        "e: 0.10",
        "f: 123456789012345678901234567890",
    ]


@pytest.mark.parametrize(
    ("key", "path"),
    [
        ("a.b", '["a.b"]'),
        ("[0]", '["[0]"]'),
        ("", '[""]'),
        ("1", '["1"]'),
        ("@id", '["@id"]'),
        ("$", '["$"]'),
        ('say "hi"', '["say \\"hi\\""]'),
        ("x: y", '["x: y"]'),
        ("line\nbreak", '["line\\nbreak"]'),
        ("sep\u2028arator", '["sep\\u2028arator"]'),
        ("café", '["café"]'),
        ("plain_key-2", "plain_key-2"),
    ],
)
def test_json_leaf_text_paths_quote_every_non_plain_key(key, path):
    text, _ = json_to_leaf_text(json.dumps({key: 1}))

    assert text == f"{path}: 1"
    if path.startswith("["):
        assert json.loads(path[1:-1]) == key


def test_json_leaf_text_paths_are_unambiguous_for_dotted_and_bracketed_keys():
    text, _ = json_to_leaf_text(
        '{"a":{"b":1},"a.b":2,"c":[3],"c[0]":4,"d":{"0":5},"e":[[6]]}'
    )

    assert text.splitlines() == [
        "a.b: 1",
        '["a.b"]: 2',
        "c[0]: 3",
        '["c[0]"]: 4',
        'd["0"]: 5',
        "e[0][0]: 6",
    ]


def test_json_leaf_text_renders_empty_containers_and_root_scalars():
    assert json_to_leaf_text('{"o":{},"a":[]}') == ("o: {}\na: []", False)
    assert json_to_leaf_text("{}") == ("$: {}", False)
    assert json_to_leaf_text("[]") == ("$: []", False)
    assert json_to_leaf_text('"value"') == ("$: value", False)
    assert json_to_leaf_text(" true ") == ("$: true", False)
    assert json_to_leaf_text("null") == ("$: null", False)
    assert json_to_leaf_text('[{"k":false}]') == ("[0].k: false", False)


def test_json_leaf_text_keeps_each_string_on_its_own_line():
    text, _ = json_to_leaf_text(
        json.dumps(
            {
                "s": "a\r\nb\rc\nd\u2028e\u2029f\x0bg\x0ch\x85i\x1cj",
                "t": "tab\tstays  doubled",
            }
        )
    )

    assert text == "s: a b c d e f g h i j\nt: tab\tstays  doubled"
    assert len(text.splitlines()) == 2


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("", "invalid json"),
        ("{", "invalid json"),
        ('{"a":1,}', "invalid json"),
        ("{'a':1}", "invalid json"),
        ('{"a":1} trailing', "invalid json"),
        ("[NaN]", "invalid json"),
        ("[-Infinity]", "invalid json"),
        ('["\\ud800"]', "invalid json"),
        ('{"\\udfff":1}', "invalid json"),
        ("\ufeff{}", "invalid json"),
        ('["raw\ncontrol"]', "invalid json"),
        ('{"a":1,"a":2}', "duplicate object key"),
        ('{"x":{"a":1,"a":1}}', "duplicate object key"),
    ],
)
def test_json_leaf_text_rejects_anything_but_strict_json(body, reason):
    with pytest.raises(JsonLeafTextError) as error:
        json_to_leaf_text(body)

    assert str(error.value) == reason


def test_json_leaf_text_rejects_nesting_beyond_the_fixed_depth():
    at_limit = "[" * source_module.JSON_MAX_DEPTH + "]" * source_module.JSON_MAX_DEPTH
    beyond = "[" * 65 + "]" * 65
    objects = '{"a":' * 65 + "1" + "}" * 65
    recursion = "[" * 200_000 + "]" * 200_000

    assert source_module.JSON_MAX_DEPTH == 64
    assert json_to_leaf_text(at_limit)[0] == "[0]" * 63 + ": []"
    for body in (beyond, objects, recursion):
        with pytest.raises(JsonLeafTextError, match="^nesting exceeds limit$"):
            json_to_leaf_text(body)


def test_json_leaf_text_bounds_value_count_before_parsing():
    assert source_module.JSON_MAX_VALUES == 1_000_000
    assert json_to_leaf_text("[1,2]", max_values=3) == ("[0]: 1\n[1]: 2", False)
    with pytest.raises(JsonLeafTextError, match="^value count exceeds limit$"):
        json_to_leaf_text("[1,2,3]", max_values=3)
    # The pre-parse bound also counts separators inside strings: conservative.
    with pytest.raises(JsonLeafTextError, match="^value count exceeds limit$"):
        json_to_leaf_text('["a,b,c"]', max_values=3)
    # It is checked before parsing, so it wins over a later syntax error.
    with pytest.raises(JsonLeafTextError, match="^value count exceeds limit$"):
        json_to_leaf_text("[1,2,3,", max_values=3)


def test_json_leaf_text_truncates_at_the_character_limit():
    full, _ = json_to_leaf_text(STUDY.decode())

    text, truncated = json_to_leaf_text(STUDY.decode(), max_characters=60)
    exact, exact_truncated = json_to_leaf_text(
        STUDY.decode(), max_characters=len(full)
    )

    assert truncated is True
    assert text == full[:60]
    assert (exact, exact_truncated) == (full, False)


def test_json_leaf_text_validity_does_not_depend_on_the_truncation_point():
    body = '{"a":"' + "x" * 100 + '","late":"\\ud800"}'

    with pytest.raises(JsonLeafTextError, match="^invalid json$"):
        json_to_leaf_text(body, max_characters=10)


def test_json_leaf_text_bounds_rendering_of_amplifying_paths():
    key = "k" * 10_000
    body = json.dumps({key: list(range(5_000))})

    text, truncated = json_to_leaf_text(body, max_characters=50_000)

    assert truncated is True
    assert len(text) == 50_000
    assert text.startswith(f"{key}[0]: 0\n{key}[1]: 1\n")


# --- HTTP resolver -----------------------------------------------------------


def test_http_resolver_extracts_json_with_versioned_extractor_provenance():
    result = _resolve(STUDY)

    assert result.ok is True
    source = result.source
    assert source.text == STUDY_TEXT
    assert source.media_type == "application/json"
    window = source.evidence_window
    assert window.truncation == "complete"
    assert window.original_bytes == len(STUDY)
    assert window.original_characters == len(STUDY.decode())
    assert window.captured_characters == len(STUDY_TEXT)
    assert window.captured_bytes == len(STUDY_TEXT.encode())
    identity = window.to_dict()
    assert identity["schema"] == "groundnut-evidence-window/v2"
    assert identity["extraction_method"] == "json-leaf-text/v1:charset=utf-8"
    assert identity["extractor"] == {
        "name": "json-leaf-text",
        "version": "1",
        "parameters": {
            "charset": "utf-8",
            "max_characters": source_module.DEFAULT_MAX_EXTRACTED_CHARACTERS,
            "max_depth": 64,
            "max_values": 1_000_000,
        },
    }
    assert identity["extractor_library"] is None
    assert identity["runtime"]["name"] == "python"


@pytest.mark.parametrize(
    ("body", "failure", "detail"),
    [
        (b'{"protocolSection":', "source_media_unsupported", "application/json: invalid json"),
        (b"[NaN]", "source_media_unsupported", "application/json: invalid json"),
        (
            b'{"a":1,"a":2}',
            "source_media_unsupported",
            "application/json: duplicate object key",
        ),
        (
            b"[" * 65 + b"]" * 65,
            "source_media_unsupported",
            "application/json: nesting exceeds limit",
        ),
        (
            b"[" * 200_000 + b"]" * 200_000,
            "source_media_unsupported",
            "application/json: nesting exceeds limit",
        ),
        (
            b"[" + b"0," * 1_000_000 + b"0]",
            "source_too_large",
            "application/json: value count exceeds limit",
        ),
    ],
)
def test_http_resolver_fails_closed_on_json_it_cannot_extract(body, failure, detail):
    result = _resolve(body)

    assert result.ok is False
    assert result.failure == failure
    assert result.detail == detail
    assert result.detail in source_module.JSON_FAILURE_DETAILS


def test_http_resolver_json_window_declares_character_truncation():
    result = _resolve(STUDY, max_extracted_characters=60)

    window = result.source.evidence_window
    assert result.source.text == STUDY_TEXT[:60]
    assert window.truncation == "truncated"
    assert window.captured_characters == 60
    assert window.original_characters == len(STUDY.decode())
    assert window.extractor["parameters"]["max_characters"] == 60


def test_http_resolver_json_lossy_decode_is_not_declared_complete():
    body = STUDY.replace(b"Geometric", b"Geo\xffmetric")

    result = _resolve(body)

    assert result.ok is True
    assert "\ufffd" in result.source.text
    assert result.source.evidence_window.truncation == "unknown"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'{"message":"not found"}', "sparse"),
        (b'{"messages":[{"status":"no posts found"}],"collection":[]}', "sparse"),
        (b'{"count":0}', "sparse"),
        (b'{"error":"Too many requests"}', "hollow"),
        (b'{"detail":"Access denied"}', "hollow"),
        (b"{}", "empty"),
        (b"[]", "empty"),
        (b"null", "empty"),
        (b'"   "', "empty"),
        (STUDY, "complete"),
        (EUROPE_PMC, "complete"),
    ],
)
def test_json_window_classification_fails_closed_on_tiny_envelopes(body, expected):
    result = _resolve(body)

    assert result.ok is True
    assert result.source.evidence_window.truncation == expected


def test_sparse_and_hollow_json_windows_never_prove_quote_absence():
    reference = SourceReference("fixture", STUDY_URI)
    for body in (b'{"message":"not found"}', b'{"error":"Too many requests"}'):
        result = _resolve(body)
        absent = verify_claim(
            Claim("absent", "Status.", source=reference, excerpt="COMPLETED"),
            result,
        )
        assert absent.outcome == "evidence_window_incomplete"
    hollow = _resolve(b'{"error":"Too many requests"}')
    echoed = verify_claim(
        Claim("echo", "Echo.", source=reference, excerpt="Too many requests"),
        hollow,
    )
    assert echoed.outcome == "evidence_window_incomplete"


def test_json_window_quote_check_finds_values_and_reports_absence():
    reference = SourceReference("fixture", STUDY_URI)
    result = _resolve(STUDY)

    def check(excerpt):
        return verify_claim(
            Claim("c", "Claim.", source=reference, excerpt=excerpt), result
        )

    assert check("COMPLETED").method == "byte_exact"
    assert check("enrollmentInfo.count: 47079").outcome == "excerpt_found"
    assert check("243.40").outcome == "excerpt_found"
    assert check("Café Research São Paulo").outcome == "excerpt_found"
    assert check("Second sentence. Third.").method == "byte_exact"
    assert check("TERMINATED").outcome == "excerpt_not_found"


def test_json_snapshot_replays_text_and_window_byte_for_byte(tmp_path):
    reference = SourceReference("fixture", STUDY_URI)
    live = _resolve(STUDY)
    store = SnapshotStore(tmp_path)
    store.archive(live.source)
    before = store.path_for(reference.uri).read_bytes()

    first = store.load(reference)
    second = store.load(reference)

    assert first.ok and second.ok
    assert first.detail is None
    assert first.source.text == second.source.text == live.source.text
    assert (
        json.dumps(first.source.evidence_window.to_dict(), sort_keys=True)
        == json.dumps(second.source.evidence_window.to_dict(), sort_keys=True)
        == json.dumps(live.source.evidence_window.to_dict(), sort_keys=True)
    )
    assert store.path_for(reference.uri).read_bytes() == before


def test_json_snapshot_window_tampering_fails_closed(tmp_path):
    reference = SourceReference("fixture", STUDY_URI)
    store = SnapshotStore(tmp_path)
    store.archive(_resolve(STUDY).source)
    path = store.path_for(reference.uri)
    snapshot = json.loads(path.read_text())
    snapshot["evidence_window"]["extractor"]["parameters"]["max_depth"] = 128
    path.write_text(json.dumps(snapshot, sort_keys=True))

    loaded = store.load(reference)

    assert loaded.failure == "source_changed"
    assert loaded.detail == "snapshot_evidence_window_invalid"


def test_html_and_text_extraction_methods_are_unchanged():
    html = _resolve(b"<p>Source <b>fact</b></p>", media_type="text/html")
    text = _resolve(b'{"raw": "json as text"}', media_type="text/plain")

    assert (
        html.source.evidence_window.extraction_method
        == "html.parser-visible-text/v2:charset=utf-8"
    )
    assert text.source.text == '{"raw": "json as text"}'
    assert text.source.evidence_window.extraction_method == "http-text/v2:charset=utf-8"
    assert set(text.source.evidence_window.extractor["parameters"]) == {
        "charset",
        "max_characters",
    }


# --- read-time capture -------------------------------------------------------


def test_capture_declaration_admits_application_json():
    declaration = _json_declaration("text/html")
    replayed = CaptureDeclaration.from_mapping(declaration.to_dict())

    assert declaration.to_dict()["media_types"] == ["application/json", "text/html"]
    assert replayed == declaration
    assert replayed.sha256 == declaration.sha256
    with pytest.raises(ValueError, match="unsupported declared media types"):
        CaptureDeclaration("public_api", ("application/ld+json",))


@pytest.mark.parametrize(
    ("served", "declared"),
    [("application/json", ("text/html", "application/pdf")), ("text/html", ("application/json",))],
)
def test_declared_media_type_match_remains_strict(tmp_path, served, declared):
    body = STUDY if served == "application/json" else b"<main>Status</main>"
    resolver = _resolver(_Opener({STUDY_URI: body}, served))
    store = SnapshotStore(tmp_path)

    receipt = ReadTimeCaptureProducer(
        store, resolver, CaptureDeclaration("public_api", declared)
    ).capture(SourceReference("study", STUDY_URI))

    result = receipt["acquisition"]["result"]
    assert result["ok"] is False
    assert result["failure"] == "source_media_unsupported"
    assert result["detail"].startswith("declared_media_type_mismatch;detail_ref=sha256:")
    assert result["evidence_window"] is None
    assert "COMPLETED" not in store.path_for(STUDY_URI).read_text()


def test_json_extraction_failure_keeps_its_fixed_detail_through_capture(tmp_path):
    resolver = _resolver(_Opener({STUDY_URI: b'{"protocolSection":'}))
    store = SnapshotStore(tmp_path)

    receipt = ReadTimeCaptureProducer(store, resolver, _json_declaration()).capture(
        SourceReference("study", STUDY_URI)
    )

    result = receipt["acquisition"]["result"]
    assert result["failure"] == "source_media_unsupported"
    assert result["detail"] == "application/json: invalid json"
    replay = SnapshotFirstResolver(store, mode="replay_only").resolve(
        SourceReference("study", STUDY_URI)
    )
    assert (replay.failure, replay.detail) == (
        "source_media_unsupported",
        "application/json: invalid json",
    )


def test_json_capture_request_round_trip_replays_the_identical_window(
    tmp_path, monkeypatch
):
    opener = _Opener({STUDY_URI: STUDY, EUROPE_PMC_URI: EUROPE_PMC})
    monkeypatch.setattr(capture_module, "HttpResolver", lambda: _resolver(opener))
    request = {
        "schema": "groundnut-read-capture-request/v2",
        "snapshot_directory": "snapshots",
        "declaration": {
            "connector": "public_api",
            "intent": "evidence_verification",
            "media_types": ["application/json"],
            "retained_query_parameters_by_host": {
                "europepmc.example.test": ["format", "query", "resultType"],
            },
        },
        "sources": [
            {"source_id": "trial", "uri": STUDY_URI},
            {"source_id": "article", "uri": EUROPE_PMC_URI},
        ],
    }

    batch = execute_request(request, base_directory=tmp_path, allow_live=True)
    again = execute_request(request, base_directory=tmp_path, allow_live=True)

    assert opener.requested == [STUDY_URI, EUROPE_PMC_URI]
    declaration = CaptureDeclaration.from_mapping(request["declaration"])
    store = SnapshotStore(tmp_path / "snapshots")
    for receipt, repeat, uri in zip(
        batch["receipts"], again["receipts"], (STUDY_URI, EUROPE_PMC_URI)
    ):
        validate_capture_receipt(receipt)
        assert receipt["acquisition"]["strategy"] == "live_archived"
        assert repeat["acquisition"]["strategy"] == "snapshot"
        captured = receipt["acquisition"]["result"]
        assert captured["ok"] is True
        assert captured["evidence_window"]["truncation"] == "complete"
        assert captured["evidence_window"]["extraction_method"] == (
            "json-leaf-text/v1:charset=utf-8"
        )
        assert repeat["acquisition"]["result"] == captured

        first = resolve_snapshot(SourceReference("cited", uri), declaration, store)
        second = resolve_snapshot(SourceReference("cited", uri), declaration, store)
        assert first.ok is True
        assert first.source.media_type == "application/json"
        assert first.evidence_window.to_dict() == captured["evidence_window"]
        assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
            second.to_dict(), sort_keys=True
        )

    europe = resolve_snapshot(
        SourceReference("cited", EUROPE_PMC_URI), declaration, store
    )
    assert europe.canonical_reference.uri == EUROPE_PMC_URI.replace(
        "?query=EXT_ID%3A00000000&resultType=core&format=json",
        "?format=json&query=EXT_ID%3A00000000&resultType=core",
    )
    assert "resultList.result[0].abstractText: Efficacy was 95.0%" in europe.source.text
    trial = resolve_snapshot(SourceReference("cited", STUDY_URI), declaration, store)
    assert trial.source.text == STUDY_TEXT


def test_json_capture_feeds_the_ic_ledger_quote_check(tmp_path):
    from groundnut.ic_loop import run_loop

    out = tmp_path / "loop"
    store = SnapshotStore(out / "snapshots")
    receipt = ReadTimeCaptureProducer(
        store, _resolver(_Opener({STUDY_URI: STUDY})), _json_declaration()
    ).capture(SourceReference("trial", STUDY_URI))
    assert receipt["acquisition"]["result"]["ok"] is True
    report = tmp_path / "report.md"
    report.write_text(
        "---\ntitle: JSON evidence memo\n---\n\n# Trial status\n\n"
        f'The registry lists the trial as [completed]({STUDY_URI} "Source") '
        "<!-- ic-source-quote: overallStatus: COMPLETED --> after follow-up.\n\n"
        f'The registry records [the final enrollment]({STUDY_URI} "Source") '
        "<!-- ic-source-quote: enrollmentInfo.count: 47079 --> for the study.\n\n"
        f'The registry says the trial was [stopped early]({STUDY_URI} "Source") '
        "<!-- ic-source-quote: TERMINATED --> for futility.\n"
    )

    summary = run_loop(report, out, replay_only=True)
    ledger = json.loads((out / "ledger.json").read_text())

    assert summary["evidence_window_incomplete"] == 0
    assert ledger["counts"]["by_detail"] == {
        "excerpt_found:found_byte_exact": 2,
        "citation_unconfirmed:excerpt_not_found": 1,
    }
    assert [
        (row["text"], row["bucket"], row["anchor_method"]) for row in ledger["rows"]
    ] == [
        (
            "The registry lists the trial as completed after follow-up.",
            "excerpt_found",
            "byte_exact",
        ),
        (
            "The registry records the final enrollment for the study.",
            "excerpt_found",
            "byte_exact",
        ),
        (
            "The registry says the trial was stopped early for futility.",
            "citation_unconfirmed",
            "fuzzy",
        ),
    ]
    run = json.loads((out / "run.json").read_text())
    [acquisition] = run["execution"]["run"]["acquisitions"]
    assert acquisition["strategy"] == "snapshot"
    assert acquisition["result"]["evidence_window"]["extraction_method"] == (
        "json-leaf-text/v1:charset=utf-8"
    )

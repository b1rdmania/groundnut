"""JSON sources: json-leaf-text/v1 extraction, capture admission and replay.

Every body here is a synthetic fixture shaped like a public life-science API
record (ClinicalTrials.gov v2, bioRxiv details, Europe PMC search). Transport
is injected; no test opens a socket.
"""

import json
from pathlib import Path
import random
import re
import subprocess
import sys
import textwrap
import tracemalloc

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


def _run_isolated(code, *, timeout):
    """Run code in a fresh interpreter: a crash or hang fails the test only."""

    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_deep_json_fails_closed_on_a_small_thread_stack():
    # Before the pre-parse scan, the C parser recursed ~10,000 levels on a
    # 10 KB body before the depth check ran and crashed a 512 KiB thread.
    completed = _run_isolated(
        """
        import threading
        threading.stack_size(512 * 1024)
        from groundnut.sources import (
            HttpResolver, JsonLeafTextError, SourceReference, json_to_leaf_text,
        )

        class Headers:
            def get_content_type(self):
                return "application/json"
            def get(self, name, default=None):
                return default

        class Response:
            status = 200
            headers = Headers()
            def __init__(self, body):
                self.body = body
            def read(self, size=-1):
                return self.body
            def geturl(self):
                return "https://example.test/deep"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        results = []

        def run():
            for depth in (10_000, 100_000):
                body = "[" * depth + "]" * depth
                try:
                    json_to_leaf_text(body)
                    results.append("parsed")
                except JsonLeafTextError as error:
                    results.append(str(error))
                resolver = HttpResolver(
                    opener=lambda request, timeout: Response(body.encode()),
                    address_resolver=lambda host, port: ("93.184.216.34",),
                    allow_injected_transport=True,
                )
                resolution = resolver.resolve(
                    SourceReference("deep", "https://example.test/deep")
                )
                results.append(f"{resolution.failure}|{resolution.detail}")

        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        print(results)
        """,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(
        ["nesting exceeds limit", "source_media_unsupported|application/json: nesting exceeds limit"] * 2
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('["' + "[" * 100 + '"]', ('[0]: ' + "[" * 100, False)),
        ('["\\"' + "{" * 100 + '"]', ('[0]: "' + "{" * 100, False)),
        ('{"k\\\\":"' + "]" * 10 + '"}', ('["k\\\\"]: ' + "]" * 10, False)),
        ("[" * 64 + "]" * 64, ("[0]" * 63 + ": []", False)),
        ('{"a":' * 32 + "[" * 32 + "]" * 32 + "}" * 32, (".".join(["a"] * 32) + "[0]" * 31 + ": []", False)),
    ],
)
def test_depth_scan_ignores_brackets_inside_strings(body, expected):
    assert json_to_leaf_text(body) == expected


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("[" * 65 + "]" * 65, "nesting exceeds limit"),
        ('{"a":' * 33 + "[" * 32 + "]" * 32 + "}" * 33, "nesting exceeds limit"),
        ("[" * 65, "nesting exceeds limit"),
        ('["' + "[" * 100, "invalid json"),
        ("]" + "[" * 100, "invalid json"),
        ("[]]" + "[" * 100, "invalid json"),
    ],
)
def test_depth_scan_fails_closed_before_parsing(body, reason):
    with pytest.raises(JsonLeafTextError) as error:
        json_to_leaf_text(body)

    assert str(error.value) == reason


def test_depth_scan_is_linear_on_unterminated_escaped_quotes():
    # A backtracking string pattern is quadratic here (about 3.6 s at 32 KB,
    # four times longer per doubling); the possessive scan takes milliseconds.
    completed = _run_isolated(
        """
        from groundnut.sources import JSON_MAX_DEPTH, _json_nesting_exceeds
        body = '["' + '\\\\"' * 2_000_000 + "[" * 100
        print(_json_nesting_exceeds(body, JSON_MAX_DEPTH))
        """,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"


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


def _reference_leaf_text(body):
    """Straightforward full rendering of the documented format, for comparison."""

    document = json.loads(body, parse_int=str, parse_float=str)
    lines = []

    def step(key, at_root):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            return key if at_root else "." + key
        quoted = json.dumps(key, ensure_ascii=False)
        for character in ("\x85", "\u2028", "\u2029"):
            quoted = quoted.replace(character, f"\\u{ord(character):04x}")
        return f"[{quoted}]"

    def render(value):
        if value is True or value is False or value is None:
            return json.dumps(value)
        if isinstance(value, (dict, list)):
            return "{}" if isinstance(value, dict) else "[]"
        return re.sub("\r\n|[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]", " ", value)

    def walk(value, path):
        if isinstance(value, dict) and value:
            for key, item in value.items():
                walk(item, path + step(key, not path))
        elif isinstance(value, list) and value:
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        else:
            lines.append(f"{path or '$'}: {render(value)}")

    walk(document, "")
    return "\n".join(lines)


def _random_documents(count, seed=20261005):
    rng = random.Random(seed)
    keys = [
        "a", "b_2", "a.b", "[0]", "", "1", "$", "x: y", 'q"t', "line\nbr",
        "sep\u2028x", "caf\u00e9", "\U0001F600", "k" * 40, "back\\slash",
        "nel\x85", "ctl\x01",
    ]
    strings = [
        "", "v", "a\r\nb", "c\rd\ne", "x\u2028y\u2029z", "t\tab",
        "\U0001F600 emoji", "long " * 30, "\r\n" * 5, "end\r",
    ]

    def value(depth):
        draw = rng.random()
        if depth > 3 or draw < 0.35:
            return rng.choice([True, False, None, 0, 1.5, -2, 10**30, {}, []] + strings)
        if draw < 0.7:
            return {
                rng.choice(keys) + (str(index) if rng.random() < 0.3 else ""): value(depth + 1)
                for index in range(rng.randint(1, 4))
            }
        return [value(depth + 1) for _ in range(rng.randint(1, 4))]

    return [json.dumps(value(0), ensure_ascii=rng.random() < 0.5) for _ in range(count)]


def test_json_leaf_text_matches_the_reference_rendering_at_every_cut():
    documents = [STUDY.decode(), '"root"', "[]", "{}", '"a\\r\\nb"'] + _random_documents(60)
    for body in documents:
        full = _reference_leaf_text(body)
        # Every cut through the first lines, then a stride, then the end.
        cuts = {*range(1, 400), *range(400, len(full), 37), *range(len(full) - 3, len(full) + 3)}
        for cut in sorted(cut for cut in cuts if cut >= 1):
            assert json_to_leaf_text(body, max_characters=cut) == (
                full[:cut],
                len(full) > cut,
            ), (body, cut)


def test_json_leaf_text_quotes_long_keys_identically_across_chunk_edges():
    edge = source_module._JSON_QUOTE_CHUNK_CHARACTERS
    key = "a" * (edge - 1) + '"\u2028\x01' + "b" * edge + "\x85"
    body = json.dumps({"outer": {key: {"leaf": "v\r\nw"}}}, ensure_ascii=False)
    full = _reference_leaf_text(body)

    assert json_to_leaf_text(body) == (full, False)
    for cut in (edge - 2, edge, edge + 3, edge + 9, len(full) - 6, len(full) - 1):
        assert json_to_leaf_text(body, max_characters=cut) == (full[:cut], True)


@pytest.mark.parametrize("first_key", ["k", "\U0001F600"])
def test_json_leaf_text_memory_stays_bounded_for_deep_long_key_paths(first_key):
    # 64 containers whose keys are 20,000 characters: copying the path prefix
    # per level (the pre-fix renderer) peaked above 160 MiB here.
    keys = [first_key + "k" * 20_000] + ["k" * 20_000] * 62
    body = "".join("{" + json.dumps(key, ensure_ascii=False) + ":" for key in keys)
    body += '{"v":1}' + "}" * len(keys)

    tracemalloc.start()
    try:
        text, truncated = json_to_leaf_text(body)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert truncated is False
    assert text.endswith(".v: 1") and len(text.splitlines()) == 1
    assert peak < 32 * 1024 * 1024


def _traced_peak(function, *args, **kwargs):
    tracemalloc.start()
    try:
        result = function(*args, **kwargs)
        return result, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_json_leaf_text_never_builds_a_line_past_the_budget():
    body = json.dumps({"k" * 3_000_000: {"a": "x" * 5_000_000, "b": 1}})

    _, parse_peak = _traced_peak(json.loads, body)
    (text, truncated), render_peak = _traced_peak(
        json_to_leaf_text, body, max_characters=1_000
    )

    assert (text, truncated) == ("k" * 1_000, True)
    # Parsing holds the 8M decoded characters; rendering a 1,000-character
    # window must add almost nothing on top of that.
    assert render_peak < parse_peak + 1024 * 1024


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

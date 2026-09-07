"""Synthetic acceptance of the process boundary; no model or network calls."""

import json
import subprocess
import sys

import pytest

from groundnut.passages import execute_request, REQUEST_SCHEMA
from groundnut.provenance import sha256_text


def request(text, limit=7):
    return {
        "schema": REQUEST_SCHEMA,
        "sources": [{"source_id": "s", "text": text}],
        "max_characters": limit,
    }


def test_lossless_offsets_and_source_bound_ids():
    text = "same same\n\nαβ 😀\tlast"
    rows = execute_request(request(text))["passages"]
    assert "".join(row["exact_text"] for row in rows) == text
    assert len({r["passage_id"] for r in rows}) == len(rows)
    for row in rows:
        assert 0 < row["end"] - row["start"] <= 7
        assert text[row["start"] : row["end"]] == row["exact_text"]
        assert row["source_sha256"] == sha256_text(text)
        assert row["text_sha256"] == sha256_text(row["exact_text"])
    assert rows == execute_request(request(text))["passages"]
    assert (
        rows[0]["passage_id"]
        != execute_request(request(text + "!"))["passages"][0]["passage_id"]
    )
    repeated = execute_request(request("abab", 2))["passages"]
    assert repeated[0]["exact_text"] == repeated[1]["exact_text"]
    assert repeated[0]["passage_id"] != repeated[1]["passage_id"]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "7"])
def test_invalid_limits_rejected(value):
    with pytest.raises(ValueError):
        execute_request(request("text", value))


def test_cli_success_and_failure_are_atomic_json():
    command = [sys.executable, "-m", "groundnut.passages"]
    result = subprocess.run(
        command, input=json.dumps(request("a\nb")), text=True, capture_output=True
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == execute_request(request("a\nb"))
    payload = request("text")
    payload["sources"] *= 2
    result = subprocess.run(
        command, input=json.dumps(payload), text=True, capture_output=True
    )
    assert result.returncode == 2
    assert "passages" not in json.loads(result.stdout)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"schema": "wrong", "sources": []},
        {"schema": REQUEST_SCHEMA, "sources": []},
        {"schema": REQUEST_SCHEMA, "sources": {}},
        {"schema": REQUEST_SCHEMA, "sources": [None]},
        {"schema": REQUEST_SCHEMA, "sources": [{}]},
        {"schema": REQUEST_SCHEMA, "sources": [{"source_id": 1, "text": "a"}]},
        {"schema": REQUEST_SCHEMA, "sources": [{"source_id": "s", "text": 1}]},
        {"schema": REQUEST_SCHEMA, "sources": [{"source_id": "s", "text": ""}]},
    ],
)
def test_malformed_requests_are_rejected(payload):
    with pytest.raises(ValueError):
        execute_request(payload)


def test_request_source_order_is_preserved():
    payload = request("abc", 2)
    payload["sources"] = [{"source_id": sid, "text": "abc"} for sid in ("z", "a")]
    rows = execute_request(payload)["passages"]
    assert [(row["source_id"], row["start"]) for row in rows] == [
        ("z", 0),
        ("z", 2),
        ("a", 0),
        ("a", 2),
    ]

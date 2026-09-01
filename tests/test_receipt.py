import math

import pytest

from groundnut.receipt import canonical_json_bytes, loads_strict, sha256_json


def test_receipt_json_is_order_stable_and_strict():
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_receipt_json_rejects_non_finite_numbers(value):
    with pytest.raises(ValueError):
        canonical_json_bytes({"value": value})


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_receipt_loader_rejects_non_standard_numbers(token):
    with pytest.raises(ValueError, match="non-finite JSON number"):
        loads_strict('{"value":' + token + "}")

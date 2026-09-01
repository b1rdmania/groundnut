"""One strict canonical-JSON boundary for self-hashed Groundnut receipts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Encode canonical JSON and reject NaN/Infinity rather than minting invalid JSON."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def loads_strict(value: str | bytes | bytearray) -> Any:
    return json.loads(value, parse_constant=_reject_non_finite)


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")

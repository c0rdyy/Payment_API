from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any


def canonicalize(value: Any) -> bytes:
    return _encode(value).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonicalize(value)).hexdigest()


def _encode(value: Any) -> str:  # noqa: PLR0911
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _encode_str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            raise TypeError("cannot canonicalize non-finite Decimal")
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, float):
        raise TypeError("float is not allowed in canonical JSON, use Decimal or int")
    if isinstance(value, dict):
        return _encode_dict(value)
    if isinstance(value, list | tuple):
        return "[" + ",".join(_encode(v) for v in value) + "]"
    raise TypeError(f"cannot canonicalize value of type {type(value).__name__}")


def _encode_dict(d: dict[Any, Any]) -> str:
    items: list[tuple[str, Any]] = []
    for key, val in d.items():
        if not isinstance(key, str):
            raise TypeError(f"object keys must be strings, got {type(key).__name__}")
        items.append((key, val))
    items.sort(key=lambda kv: kv[0])
    return "{" + ",".join(_encode_str(k) + ":" + _encode(v) for k, v in items) + "}"


_ASCII_CONTROL_BOUNDARY = 0x20

_ESCAPES: dict[int, str] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _encode_str(s: str) -> str:
    out: list[str] = ['"']
    for ch in s:
        cp = ord(ch)
        if cp in _ESCAPES:
            out.append(_ESCAPES[cp])
        elif cp < _ASCII_CONTROL_BOUNDARY:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.infrastructure.idempotency.fingerprint import canonicalize, fingerprint


class TestCanonicalizationBasics:
    def test_simple_object(self) -> None:
        assert canonicalize({"a": 1}) == b'{"a":1}'

    def test_keys_are_sorted(self) -> None:
        assert canonicalize({"b": 2, "a": 1}) == b'{"a":1,"b":2}'

    def test_nested_objects_are_sorted(self) -> None:
        assert (
            canonicalize({"x": {"b": 2, "a": 1}, "y": [3, 2, 1]})
            == b'{"x":{"a":1,"b":2},"y":[3,2,1]}'
        )

    def test_null_true_false(self) -> None:
        assert canonicalize({"a": None, "b": True, "c": False}) == b'{"a":null,"b":true,"c":false}'

    def test_unicode_passthrough(self) -> None:
        assert canonicalize({"name": "Иван"}) == '{"name":"Иван"}'.encode()

    def test_string_escapes(self) -> None:
        assert canonicalize('a\nb"c') == b'"a\\nb\\"c"'

    def test_control_character_escaped(self) -> None:
        assert canonicalize("\x01") == b'"\\u0001"'


class TestNumberHandling:
    def test_int(self) -> None:
        assert canonicalize(42) == b"42"
        assert canonicalize(-7) == b"-7"

    def test_decimal_strips_trailing_zeros(self) -> None:
        assert canonicalize(Decimal("10.00")) == b"10"
        assert canonicalize(Decimal("10")) == canonicalize(Decimal("10.0000"))

    def test_decimal_preserves_significant_digits(self) -> None:
        assert canonicalize(Decimal("1.2300")) == b"1.23"

    def test_decimal_zero(self) -> None:
        assert canonicalize(Decimal("0")) == b"0"

    def test_float_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="float"):
            canonicalize(1.5)

    def test_nan_decimal_rejected(self) -> None:
        with pytest.raises(TypeError, match="non-finite"):
            canonicalize(Decimal("NaN"))


class TestRejections:
    def test_object_with_non_string_key(self) -> None:
        with pytest.raises(TypeError, match="object keys must be strings"):
            canonicalize({1: "value"})

    def test_unsupported_type(self) -> None:
        with pytest.raises(TypeError, match="cannot canonicalize"):
            canonicalize(object())


class TestFingerprintHexShape:
    def test_returns_64_hex_chars(self) -> None:
        fp = fingerprint({"amount": Decimal("10.00"), "currency": "USD"})
        assert len(fp) == 64
        int(fp, 16)

    def test_different_payloads_have_different_fingerprints(self) -> None:
        a = fingerprint({"amount": Decimal("10.00"), "currency": "USD"})
        b = fingerprint({"amount": Decimal("10.01"), "currency": "USD"})
        assert a != b

    def test_equivalent_payloads_have_same_fingerprint(self) -> None:
        a = fingerprint({"amount": Decimal("10"), "currency": "USD"})
        b = fingerprint({"currency": "USD", "amount": Decimal("10.0000")})
        assert a == b


_safe_scalars: st.SearchStrategy[Any] = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        max_size=20,
    ),
    st.decimals(
        allow_nan=False, allow_infinity=False, places=4, min_value=-(10**6), max_value=10**6
    ),
)


def _json_like(max_depth: int = 3) -> st.SearchStrategy[Any]:
    return st.recursive(
        _safe_scalars,
        lambda children: st.one_of(
            st.lists(children, max_size=5),
            st.dictionaries(
                st.text(
                    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
                    min_size=1,
                    max_size=10,
                ),
                children,
                max_size=5,
            ),
        ),
        max_leaves=10,
    )


class TestFingerprintProperties:
    @given(value=_json_like())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_fingerprint_is_deterministic(self, value: Any) -> None:
        assert fingerprint(value) == fingerprint(value)

    @given(value=_json_like())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_canonicalize_matches_fingerprint(self, value: Any) -> None:
        import hashlib  # noqa: PLC0415

        assert fingerprint(value) == hashlib.sha256(canonicalize(value)).hexdigest()

    @given(
        d=st.dictionaries(st.text(min_size=1, max_size=8), _safe_scalars, min_size=2, max_size=5)
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_key_reordering_is_invariant(self, d: dict[str, Any]) -> None:
        reversed_dict = {k: d[k] for k in reversed(list(d.keys()))}
        assert fingerprint(d) == fingerprint(reversed_dict)

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.exceptions import InvalidMoney
from app.domain.money import Money


class TestMoneyConstruction:
    def test_valid_amount_and_currency(self) -> None:
        m = Money(Decimal("10.00"), "USD")
        assert m.amount == Decimal("10.0000")
        assert m.currency == "USD"

    def test_quantizes_to_four_decimal_places(self) -> None:
        m = Money(Decimal("1.234567"), "USD")
        assert m.amount == Decimal("1.2346")

    def test_quantizes_equivalent_amounts_to_same_value(self) -> None:
        assert Money(Decimal("10"), "USD") == Money(Decimal("10.00"), "USD")

    def test_is_frozen(self) -> None:
        m = Money(Decimal("5"), "EUR")
        with pytest.raises(AttributeError):
            m.amount = Decimal("6")  # type: ignore[assignment]

    def test_is_hashable(self) -> None:
        s = {Money(Decimal("1"), "USD"), Money(Decimal("1"), "USD")}
        assert len(s) == 1


class TestMoneyValidation:
    @pytest.mark.parametrize("bad_amount", [Decimal("0"), Decimal("-1"), Decimal("-0.0001")])
    def test_rejects_non_positive_amount(self, bad_amount: Decimal) -> None:
        with pytest.raises(InvalidMoney, match="positive"):
            Money(bad_amount, "USD")

    def test_rejects_float_amount(self) -> None:
        with pytest.raises(InvalidMoney, match="Decimal"):
            Money(10.0, "USD")  # type: ignore[arg-type]

    def test_rejects_int_amount(self) -> None:
        with pytest.raises(InvalidMoney, match="Decimal"):
            Money(10, "USD")  # type: ignore[arg-type]

    def test_rejects_nan(self) -> None:
        with pytest.raises(InvalidMoney):
            Money(Decimal("NaN"), "USD")

    def test_rejects_infinity(self) -> None:
        with pytest.raises(InvalidMoney):
            Money(Decimal("Infinity"), "USD")

    @pytest.mark.parametrize("bad_currency", ["us", "USDX", "12A", "", "us "])
    def test_rejects_malformed_currency(self, bad_currency: str) -> None:
        with pytest.raises(InvalidMoney):
            Money(Decimal("1"), bad_currency)

    def test_rejects_lowercase_currency(self) -> None:
        with pytest.raises(InvalidMoney, match="uppercase"):
            Money(Decimal("1"), "usd")


class TestMoneyArithmetic:
    def test_addition_same_currency(self) -> None:
        result = Money(Decimal("1.50"), "USD") + Money(Decimal("2.50"), "USD")
        assert result == Money(Decimal("4.00"), "USD")

    def test_subtraction_same_currency(self) -> None:
        result = Money(Decimal("5"), "USD") - Money(Decimal("3"), "USD")
        assert result == Money(Decimal("2"), "USD")

    def test_subtraction_to_zero_or_below_raises(self) -> None:
        with pytest.raises(InvalidMoney):
            Money(Decimal("3"), "USD") - Money(Decimal("3"), "USD")

    def test_addition_mixed_currency_raises(self) -> None:
        with pytest.raises(InvalidMoney, match="mixed currencies"):
            Money(Decimal("1"), "USD") + Money(Decimal("1"), "EUR")

    def test_comparison_same_currency(self) -> None:
        assert Money(Decimal("1"), "USD") < Money(Decimal("2"), "USD")
        assert Money(Decimal("2"), "USD") <= Money(Decimal("2"), "USD")

    def test_comparison_mixed_currency_raises(self) -> None:
        with pytest.raises(InvalidMoney):
            _ = Money(Decimal("1"), "USD") < Money(Decimal("1"), "EUR")

    def test_str_format(self) -> None:
        assert str(Money(Decimal("9.99"), "USD")) == "9.9900 USD"

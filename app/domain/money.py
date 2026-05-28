from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from app.domain.exceptions import InvalidMoney

_CURRENCY_PATTERN_LEN: Final = 3
_QUANTUM: Final = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class Money:
    """Денежная сумма в одной валюте"""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise InvalidMoney(f"amount must be Decimal, got {type(self.amount).__name__}")
        if self.amount.is_nan() or self.amount.is_infinite():
            raise InvalidMoney("amount must be a finite number")
        if self.amount <= Decimal(0):
            raise InvalidMoney(f"amount must be positive, got {self.amount}")

        if not isinstance(self.currency, str):
            raise InvalidMoney("currency must be a string")
        if len(self.currency) != _CURRENCY_PATTERN_LEN or not self.currency.isalpha():
            raise InvalidMoney(f"currency must be a 3-letter ISO code, got {self.currency!r}")
        if self.currency != self.currency.upper():
            raise InvalidMoney("currency must be uppercase")

        object.__setattr__(
            self,
            "amount",
            self.amount.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN),
        )

    def __add__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount <= other.amount

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def _check_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise InvalidMoney(
                f"cannot operate on mixed currencies: {self.currency} vs {other.currency}"
            )

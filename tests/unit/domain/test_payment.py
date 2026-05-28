from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.exceptions import InvalidStateTransition
from app.domain.money import Money
from app.domain.payment import Payment, PaymentStatus


def _make_payment() -> Payment:
    return Payment.create(
        customer_id=uuid4(),
        money=Money(Decimal("10"), "USD"),
    )


class TestPaymentCreate:
    def test_starts_pending(self) -> None:
        p = _make_payment()
        assert p.status is PaymentStatus.PENDING
        assert p.version == 0
        assert p.is_terminal is False

    def test_assigns_id_and_timestamps(self) -> None:
        p = _make_payment()
        assert p.id is not None
        assert p.created_at == p.updated_at

    def test_metadata_default_is_independent_per_instance(self) -> None:
        a = _make_payment()
        b = _make_payment()
        a.metadata["key"] = "value"
        assert b.metadata == {}


class TestPaymentTransitions:
    def test_pending_to_succeeded(self) -> None:
        p = _make_payment()
        original_updated = p.updated_at
        p.mark_succeeded(provider_reference="ch_123")
        assert p.status is PaymentStatus.SUCCEEDED
        assert p.provider_reference == "ch_123"
        assert p.version == 1
        assert p.updated_at >= original_updated
        assert p.is_terminal is True

    def test_pending_to_failed(self) -> None:
        p = _make_payment()
        p.mark_failed(reason="card_declined", provider_reference="ch_456")
        assert p.status is PaymentStatus.FAILED
        assert p.failure_reason == "card_declined"
        assert p.provider_reference == "ch_456"
        assert p.version == 1
        assert p.is_terminal is True

    def test_succeeded_cannot_transition(self) -> None:
        p = _make_payment()
        p.mark_succeeded(provider_reference="ch_1")
        with pytest.raises(InvalidStateTransition):
            p.mark_succeeded(provider_reference="ch_2")
        with pytest.raises(InvalidStateTransition):
            p.mark_failed(reason="late_failure")

    def test_failed_cannot_transition(self) -> None:
        p = _make_payment()
        p.mark_failed(reason="declined")
        with pytest.raises(InvalidStateTransition):
            p.mark_succeeded(provider_reference="ch_1")

    def test_failed_without_reference_keeps_existing(self) -> None:
        p = _make_payment()
        p.mark_failed(reason="declined")
        assert p.provider_reference is None

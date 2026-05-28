from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.exceptions import InvalidStateTransition
from app.domain.money import Money


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


_TERMINAL: frozenset[PaymentStatus] = frozenset({PaymentStatus.SUCCEEDED, PaymentStatus.FAILED})


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Payment:
    id: UUID
    customer_id: UUID
    money: Money
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    version: int = 0
    provider_reference: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        customer_id: UUID,
        money: Money,
        metadata: dict[str, str] | None = None,
    ) -> Payment:
        now = _utcnow()
        return cls(
            id=uuid4(),
            customer_id=customer_id,
            money=money,
            status=PaymentStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def mark_succeeded(self, *, provider_reference: str) -> None:
        self._transition(PaymentStatus.SUCCEEDED)
        self.provider_reference = provider_reference

    def mark_failed(self, *, reason: str, provider_reference: str | None = None) -> None:
        self._transition(PaymentStatus.FAILED)
        self.failure_reason = reason
        if provider_reference is not None:
            self.provider_reference = provider_reference

    def _transition(self, target: PaymentStatus) -> None:
        if self.status != PaymentStatus.PENDING:
            raise InvalidStateTransition(current=self.status.value, attempted=target.value)
        self.status = target
        self.updated_at = _utcnow()
        self.version += 1

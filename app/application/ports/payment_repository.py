from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.domain.payment import Payment


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Запись одной попытки списания через провайдера"""

    payment_id: UUID
    attempt_no: int
    request_body: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    response: dict[str, Any] | None = None
    provider_status: str | None = None
    error: str | None = None


class PaymentRepository(Protocol):
    """Доступ на чтение и запись к агрегату Payment"""

    async def get(self, payment_id: UUID) -> Payment | None: ...

    async def add(self, payment: Payment) -> None:
        """Вставить новый платеж"""

    async def update(self, payment: Payment) -> None:
        """Сохранить изменения через оптимистичную конкуренцию"""

    async def record_attempt(self, attempt: AttemptRecord) -> None:
        """Сохранить строку в `payment_attempts`"""


class ConcurrencyError(Exception):
    """Конфликт: платеж изменил кто-то еще"""

    def __init__(self, payment_id: UUID, expected_version: int) -> None:
        super().__init__(
            f"payment {payment_id} was modified concurrently (expected version {expected_version})"
        )
        self.payment_id = payment_id
        self.expected_version = expected_version

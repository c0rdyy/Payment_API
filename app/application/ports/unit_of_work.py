from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.idempotency_repository import IdempotencyRepository
from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.payment_repository import PaymentRepository


class UnitOfWork(Protocol):
    payments: PaymentRepository
    idempotency: IdempotencyRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

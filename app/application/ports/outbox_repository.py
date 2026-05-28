from __future__ import annotations

from typing import Protocol

from app.domain.outbox import OutboxEvent


class OutboxRepository(Protocol):
    async def add(self, event: OutboxEvent) -> None:
        """Поставить событие в очередь в текущей транзакции"""

    async def claim_batch(self, *, limit: int) -> list[OutboxEvent]: ...

    async def mark_processed(self, event: OutboxEvent) -> None: ...

    async def mark_failed(self, event: OutboxEvent) -> None: ...

    async def count_unprocessed(self) -> int: ...

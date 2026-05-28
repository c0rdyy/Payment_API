from __future__ import annotations

from typing import Protocol

from app.domain.idempotency import IdempotencyRecord


class IdempotencyRepository(Protocol):
    """Порт хранения записей идемпотентности"""

    async def insert_if_absent(self, record: IdempotencyRecord) -> bool:
        """Попытаться забрать ключ.

        Вернуть True, если запись вставлена, и False, если ключ уже существовал.
        """

    async def get(self, key: str) -> IdempotencyRecord | None:
        """Прочитать текущую запись независимо от статуса."""

    async def acquire_lock(self, key: str) -> None:
        """Ждать, пока текущая транзакция не получит advisory lock для ключа.

        Lock освобождается автоматически при commit или rollback транзакции.
        """

    async def complete(self, record: IdempotencyRecord) -> None:
        """Сохранить закешированный ответ и пометить ключ completed"""

    async def list_stuck(
        self, *, older_than_seconds: int, limit: int = 100
    ) -> list[IdempotencyRecord]: ...

"""Исключения, связанные с доменной логикой."""

from __future__ import annotations


class DomainError(Exception):
    """Базовый класс для всех нарушений доменных правил"""


class InvalidMoney(DomainError):
    """Money получил некорректную сумму или валюту"""


class InvalidStateTransition(DomainError):
    """Попытка перевести сущность в недопустимое состояние"""

    def __init__(self, *, current: str, attempted: str) -> None:
        super().__init__(f"cannot transition payment from {current!r} to {attempted!r}")
        self.current = current
        self.attempted = attempted


class IdempotencyKeyMissing(DomainError):
    """В запросе нет обязательного заголовка Idempotency-Key"""


class IdempotencyConflict(DomainError):
    """Предыдущий запрос с тем же ключом еще выполняется"""

    def __init__(self, key: str) -> None:
        super().__init__(f"idempotency key {key!r} is already in progress")
        self.key = key


class FingerprintMismatch(DomainError):
    """Тот же ключ использовали с другим телом запроса"""

    def __init__(self, key: str) -> None:
        super().__init__(f"idempotency key {key!r} reused with different request body")
        self.key = key


class IdempotencyRecordExpired(DomainError):
    """Закешированная idempotency-запись пережила свой TTL"""

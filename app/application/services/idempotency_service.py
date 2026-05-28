"""IdempotencyService - управляет идемпотентными запросами, обеспечивая атомарность и согласованность.

Алгоритм состоит из двух фаз: одна для первого обработчика, другая для ожидающих.

    Фаза A (исполнитель):
    1. Попытаться вставить запись с данным ключом и статусом IN_PROGRESS.
    Если запись уже есть, значит кто-то другой выполняет запрос, и мы переходим к фазе B.
    2. Захватить блокировку для этого ключа. Это гарантирует, что даже если после
    вставки записи произойдет откат, другой обработчик не сможет начать выполнение,
    так как блокировка будет удерживаться до конца транзакции.
    3. Выполнить действие и получить результат.
    4. Обновить запись, установив статус COMPLETED и сохранив результатта.
    5. Зафиксировать транзакцию, что автоматически освободит блокировку.

    Фаза B (ожидающие):
    1. Захватить блокировку для данного ключа. Это гарантирует, что мы не будем читать
    незавершенные данные, если исполнитель еще не закончил.
    2. Прочитать запись для данного ключа.
    3. Если запись отсутствует, значит исполнитель откатился после вставки, и ключ снова
    свободен. В этом случае мы не можем быть исполнителем, так как не первый запрос, и должны
    вернуть ошибку конфликта.
    4. Если fingerprint не совпадает, значит это другой запрос с таким же ключом,
    и мы должны вернуть ошибку конфликта.
    5. Если статус COMPLETED, вернуть закешированный результат.
    6. Если статус IN_PROGRESS, значит другой запрос с таким же fingerprint уже выполняется,
    и мы должны вернуть ошибку конфликта.

Этот алгоритм гарантирует, что только один запрос с данным ключом будет выполняться одновременно, и все остальные будут либо получать результат этого запроса, либо ошибку конфликта, если это другой запрос.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from app.application.ports.unit_of_work import UnitOfWork
from app.core.metrics import IDEMPOTENCY_HITS_TOTAL
from app.domain.exceptions import (
    FingerprintMismatch,
    IdempotencyConflict,
)
from app.domain.idempotency import IdempotencyRecord, IdempotencyStatus


@dataclass(slots=True)
class IdempotentResponse:
    """Результат идемпотентного действия.

    `status` и `body` кешируются как есть и возвращаются на повторные запросы.
    """

    status: int
    body: dict[str, Any]
    payment_id: UUID


Action = Callable[[UnitOfWork], Awaitable[IdempotentResponse]]
UnitOfWorkFactory = Callable[[], UnitOfWork]


class IdempotencyService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        ttl: timedelta,
    ) -> None:
        self._uow_factory = uow_factory
        self._ttl = ttl

    async def execute(
        self,
        *,
        key: str,
        request_fingerprint: str,
        action: Action,
    ) -> IdempotentResponse:
        record = IdempotencyRecord.start(
            key=key,
            request_fingerprint=request_fingerprint,
            ttl=self._ttl,
        )

        # Фаза A: попытаться стать исполнителем для этого ключа,
        # вставив запись и захватив блокировку
        async with self._uow_factory() as uow:
            claimed = await uow.idempotency.insert_if_absent(record)
            if claimed:
                await uow.idempotency.acquire_lock(key)
                response = await action(uow)
                record.complete(
                    response_status=response.status,
                    response_body=response.body,
                    payment_id=response.payment_id,
                )
                await uow.idempotency.complete(record)
                await uow.commit()
                IDEMPOTENCY_HITS_TOTAL.labels(outcome="claimed").inc()
                return response
            # Roll back the failed INSERT attempt before re-entering.
            await uow.rollback()

        # Фаза B: мы ждем. Блокируем advisory lock до тех пор, пока
        # тот, кто захватил ключ, не зафиксирует или не откатит транзакцию, затем читаем.
        async with self._uow_factory() as uow:
            await uow.idempotency.acquire_lock(key)
            existing = await uow.idempotency.get(key)
            if existing is None:
                # Фаза A откатилась после вставки записи, но до захвата блокировки.
                # Ключ снова свободен, но мы не можем быть исполнителем,
                # так как не первый запрос
                IDEMPOTENCY_HITS_TOTAL.labels(outcome="conflict").inc()
                raise IdempotencyConflict(key)
            if not existing.matches_fingerprint(request_fingerprint):
                IDEMPOTENCY_HITS_TOTAL.labels(outcome="mismatch").inc()
                raise FingerprintMismatch(key)
            if existing.status is IdempotencyStatus.COMPLETED:
                IDEMPOTENCY_HITS_TOTAL.labels(outcome="cached").inc()
                return _to_response(existing)
            # Идемпотентный запрос с таким же fingerprint уже выполняется,
            # значит этот запрос — конфликт
            IDEMPOTENCY_HITS_TOTAL.labels(outcome="conflict").inc()
            raise IdempotencyConflict(key)


def _to_response(record: IdempotencyRecord) -> IdempotentResponse:
    if record.response_status is None or record.response_body is None or record.payment_id is None:
        raise RuntimeError(
            f"completed idempotency record {record.key!r} is missing cached response"
        )
    return IdempotentResponse(
        status=record.response_status,
        body=record.response_body,
        payment_id=record.payment_id,
    )

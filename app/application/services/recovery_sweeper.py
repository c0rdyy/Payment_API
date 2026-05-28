"""RecoverySweeper — восстанавливает зависшие идемпотентные записи.

Запись считается зависшей, если она находится в `in_progress` дольше установленного времени.
Обычно это значит, что обработчик, который её создал, упал в процессе обработки запроса,
и она так и не была обновлена до `completed`.

Возможны два исхода:

    1. Провайдер уже обработал списание. Тогда мы можем безопасно пометить запись
    как `completed` с синтетическим телом ответа, и клиент получит корректный ответ,
    а оператору не придется разбираться с дублями в провайдере.
    2. Провайдер еще не обработал списание. Тогда мы не можем пометить запись как `completed`,
    так как это может повторить списание при повторной попытке.
    В этом случае мы оставляем запись в `in_progress`, и она будет обработана
    при следующей попытке клиента, которая уже не будет зависать, так как блокировка
    будет удерживаться до конца транзакции.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import structlog

from app.application.ports.payment_gateway import PaymentGateway
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.idempotency import IdempotencyRecord, IdempotencyStatus

UnitOfWorkFactory = Callable[[], UnitOfWork]

log = structlog.get_logger()


class RecoverySweeper:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        gateway: PaymentGateway,
        *,
        stuck_after_seconds: int,
        batch_size: int = 50,
        idle_seconds: float = 5.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._stuck_after_seconds = stuck_after_seconds
        self._batch_size = batch_size
        self._idle_seconds = idle_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            recovered = await self.run_once()
            if recovered == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self._idle_seconds)

    async def run_once(self) -> int:
        async with self._uow_factory() as uow:
            stuck = await uow.idempotency.list_stuck(
                older_than_seconds=self._stuck_after_seconds,
                limit=self._batch_size,
            )

        if not stuck:
            return 0

        recovered = 0
        for record in stuck:
            try:
                if await self._reconcile(record):
                    recovered += 1
            except Exception as e:
                log.warning(
                    "recovery.sweep.failed",
                    key=record.key,
                    error=repr(e),
                )
        return recovered

    async def _reconcile(self, record: IdempotencyRecord) -> bool:
        result = await self._gateway.lookup(record.key)
        if result is None:
            log.info(
                "recovery.sweep.no_provider_record",
                key=record.key,
                action="leave_in_progress",
            )
            return False

        synthetic_body = {
            "id": str(record.payment_id) if record.payment_id else None,
            "status": "succeeded" if result.success else "failed",
            "provider_reference": result.provider_reference,
            "failure_reason": result.failure_reason,
            "recovered": True,
        }

        async with self._uow_factory() as uow:
            existing = await uow.idempotency.get(record.key)
            if existing is None or existing.status is not IdempotencyStatus.IN_PROGRESS:
                await uow.commit()
                return False

            existing.complete(
                response_status=201,
                response_body=synthetic_body,
                payment_id=existing.payment_id or record.payment_id,
            )
            await uow.idempotency.complete(existing)
            await uow.commit()

        log.info(
            "recovery.sweep.reconciled",
            key=record.key,
            provider_reference=result.provider_reference,
            success=result.success,
        )
        return True

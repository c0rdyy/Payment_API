"""OutboxDispatcher - фоновый сервис, который читает события из таблицы outbox
и передает их в handler для доставки.

Каждая итерация:
    1. Открывает транзакцию.
    2. Забирает пачку необработанных событий через SELECT FOR UPDATE SKIP LOCKED.
    3. Передает каждое событие в handler, который отвечает за доставку.
    4. При успехе помечает событие обработанным.
    5. При ошибке увеличивает `attempts`, записывает `last_error` и оставляет
    строку для следующего прохода.
    6. Делает commit, ждет и повторяет цикл.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from app.core.metrics import OUTBOX_UNPROCESSED
from app.domain.outbox import OutboxEvent

if TYPE_CHECKING:
    from app.application.ports.unit_of_work import UnitOfWork

EventHandler = Callable[[OutboxEvent], Awaitable[None]]
UnitOfWorkFactory = Callable[[], "UnitOfWork"]

log = structlog.get_logger()


class OutboxDispatcher:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        handler: EventHandler,
        *,
        batch_size: int = 50,
        idle_seconds: float = 1.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._handler = handler
        self._batch_size = batch_size
        self._idle_seconds = idle_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            processed = await self.run_once()
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self._idle_seconds)

    async def run_once(self) -> int:
        """Обработать одну пачку и вернуть количество взятых событий"""
        async with self._uow_factory() as uow:
            events = await uow.outbox.claim_batch(limit=self._batch_size)
            if not events:
                pending = await uow.outbox.count_unprocessed()
                OUTBOX_UNPROCESSED.set(pending)
                await uow.commit()
                return 0

            for event in events:
                try:
                    await self._handler(event)
                except Exception as e:
                    event.mark_failed(error=repr(e))
                    await uow.outbox.mark_failed(event)
                    log.warning(
                        "outbox.event.failed",
                        event_id=str(event.id),
                        event_type=event.event_type,
                        attempts=event.attempts,
                        error=repr(e),
                    )
                    continue
                await uow.outbox.mark_processed(event)
                log.info(
                    "outbox.event.processed",
                    event_id=str(event.id),
                    event_type=event.event_type,
                )

            pending = await uow.outbox.count_unprocessed()
            OUTBOX_UNPROCESSED.set(pending)
            await uow.commit()
            return len(events)


async def log_handler(event: OutboxEvent) -> None:
    """Обработчик по умолчанию: только логирует событие"""
    log.info(
        "outbox.event.delivered",
        event_id=str(event.id),
        event_type=event.event_type,
        aggregate_id=str(event.aggregate_id),
    )

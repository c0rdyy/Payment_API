from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.services.outbox_dispatcher import OutboxDispatcher
from app.domain.outbox import OutboxEvent
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _uow_factory(session_factory: async_sessionmaker) -> object:
    def _factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return _factory


async def _seed_event(session_factory: async_sessionmaker, *, event_type: str) -> OutboxEvent:
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        event = OutboxEvent.create(
            aggregate_id=uuid4(),
            event_type=event_type,
            payload={"hello": "world"},
            now=datetime.now(UTC),
        )
        await uow.outbox.add(event)
        await uow.commit()
    return event


class TestOutboxDispatch:
    async def test_dispatcher_processes_pending_events(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        for _ in range(3):
            await _seed_event(session_factory, event_type="payment.succeeded")

        delivered: list[OutboxEvent] = []

        async def capture(event: OutboxEvent) -> None:
            delivered.append(event)

        dispatcher = OutboxDispatcher(_uow_factory(session_factory), capture, batch_size=10)
        processed = await dispatcher.run_once()

        assert processed == 3
        assert all(e.event_type == "payment.succeeded" for e in delivered)

        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert await uow.outbox.count_unprocessed() == 0

    async def test_handler_failure_keeps_event_pending(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        await _seed_event(session_factory, event_type="payment.succeeded")

        async def boom(_event: OutboxEvent) -> None:
            raise RuntimeError("downstream is down")

        dispatcher = OutboxDispatcher(_uow_factory(session_factory), boom, batch_size=10)
        processed = await dispatcher.run_once()
        assert processed == 1

        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert await uow.outbox.count_unprocessed() == 1
            events = await uow.outbox.claim_batch(limit=10)
            await uow.commit()
        assert all(e.attempts >= 1 for e in events)
        assert all(e.last_error and "downstream is down" in e.last_error for e in events)

    async def test_parallel_dispatchers_no_double_delivery(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        for _ in range(8):
            await _seed_event(session_factory, event_type="payment.succeeded")

        delivered: list[OutboxEvent] = []
        delivered_lock = asyncio.Lock()

        async def capture(event: OutboxEvent) -> None:
            await asyncio.sleep(0.05)
            async with delivered_lock:
                delivered.append(event)

        d1 = OutboxDispatcher(_uow_factory(session_factory), capture, batch_size=4)
        d2 = OutboxDispatcher(_uow_factory(session_factory), capture, batch_size=4)
        await asyncio.gather(d1.run_once(), d2.run_once())

        ids = [e.id for e in delivered]
        assert len(ids) == len(set(ids)), "an event was delivered twice"

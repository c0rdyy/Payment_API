from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.unit_of_work import UnitOfWork
from app.infrastructure.db.idempotency_repository import SqlAlchemyIdempotencyRepository
from app.infrastructure.db.outbox_repository import SqlAlchemyOutboxRepository
from app.infrastructure.db.repositories import SqlAlchemyPaymentRepository


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Один UoW = одна session = одна transaction"""

    payments: SqlAlchemyPaymentRepository
    idempotency: SqlAlchemyIdempotencyRepository
    outbox: SqlAlchemyOutboxRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.payments = SqlAlchemyPaymentRepository(self._session)
        self.idempotency = SqlAlchemyIdempotencyRepository(self._session)
        self.outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        try:
            if exc is not None:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UoW not entered")
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError("UoW not entered")
        await self._session.rollback()


UnitOfWorkFactory = Callable[[], SqlAlchemyUnitOfWork]


def make_uow_factory(session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWorkFactory:
    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory

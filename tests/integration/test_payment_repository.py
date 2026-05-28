from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.payment_repository import ConcurrencyError
from app.domain.money import Money
from app.domain.payment import Payment, PaymentStatus
from app.infrastructure.db.repositories import SqlAlchemyPaymentRepository

pytestmark = pytest.mark.integration


def _new_payment() -> Payment:
    return Payment.create(
        customer_id=uuid4(),
        money=Money(Decimal("12.50"), "USD"),
        metadata={"source": "test"},
    )


class TestAddAndGet:
    async def test_add_then_get_round_trips(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        original = _new_payment()
        await repo.add(original)
        await db_session.commit()

        loaded = await repo.get(original.id)
        assert loaded is not None
        assert loaded.id == original.id
        assert loaded.customer_id == original.customer_id
        assert loaded.money == original.money
        assert loaded.status is PaymentStatus.PENDING
        assert loaded.metadata == {"source": "test"}
        assert loaded.version == 0

    async def test_get_missing_returns_none(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        assert await repo.get(uuid4()) is None


class TestUpdateAndOptimisticLock:
    async def test_update_persists_state_change(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        payment = _new_payment()
        await repo.add(payment)
        await db_session.commit()

        payment.mark_succeeded(provider_reference="ch_001")
        await repo.update(payment)
        await db_session.commit()

        loaded = await repo.get(payment.id)
        assert loaded is not None
        assert loaded.status is PaymentStatus.SUCCEEDED
        assert loaded.provider_reference == "ch_001"
        assert loaded.version == 1

    async def test_concurrent_update_loses_optimistic_lock(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as setup_session:
            seed = _new_payment()
            await SqlAlchemyPaymentRepository(setup_session).add(seed)
            await setup_session.commit()

        async with session_factory() as session_a, session_factory() as session_b:
            repo_a = SqlAlchemyPaymentRepository(session_a)
            repo_b = SqlAlchemyPaymentRepository(session_b)

            payment_a = await repo_a.get(seed.id)
            payment_b = await repo_b.get(seed.id)
            assert payment_a is not None
            assert payment_b is not None

            payment_a.mark_succeeded(provider_reference="ch_a")
            payment_b.mark_failed(reason="declined")

            await repo_a.update(payment_a)
            await session_a.commit()

            with pytest.raises(ConcurrencyError):
                await repo_b.update(payment_b)
            await session_b.rollback()

        async with session_factory() as verify_session:
            loaded = await SqlAlchemyPaymentRepository(verify_session).get(seed.id)
            assert loaded is not None
            assert loaded.status is PaymentStatus.SUCCEEDED
            assert loaded.provider_reference == "ch_a"
            assert loaded.version == 1


class TestQueries:
    async def test_list_by_customer_returns_recent_first(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        customer_id = uuid4()
        async with session_factory() as session:
            repo = SqlAlchemyPaymentRepository(session)
            for _ in range(3):
                p = Payment.create(customer_id=customer_id, money=Money(Decimal("1"), "USD"))
                await repo.add(p)
                await session.flush()
                await asyncio.sleep(0.001)
            await session.commit()

            results = await repo.list_by_customer(customer_id)
            assert len(results) == 3
            timestamps = [r.created_at for r in results]
            assert timestamps == sorted(timestamps, reverse=True)

    async def test_status_counts(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyPaymentRepository(session)
            succeeded = _new_payment()
            failed = _new_payment()
            pending = _new_payment()
            for p in (succeeded, failed, pending):
                await repo.add(p)
            await session.flush()

            succeeded.mark_succeeded(provider_reference="ch_x")
            await repo.update(succeeded)
            failed.mark_failed(reason="declined")
            await repo.update(failed)
            await session.commit()

            counts = await repo.get_status_counts()
            assert counts.get(PaymentStatus.SUCCEEDED) == 1
            assert counts.get(PaymentStatus.FAILED) == 1
            assert counts.get(PaymentStatus.PENDING) == 1

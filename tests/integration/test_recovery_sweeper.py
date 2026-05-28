from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.ports.payment_gateway import (
    GatewayChargeRequest,
)
from app.application.services.recovery_sweeper import RecoverySweeper
from app.domain.idempotency import IdempotencyRecord, IdempotencyStatus
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from tests.integration.fakes.gateway import FakeGateway

pytestmark = pytest.mark.integration


def _uow_factory(session_factory: async_sessionmaker) -> object:
    def _factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return _factory


async def _seed_stuck_record(
    session_factory: async_sessionmaker,
    *,
    key: str,
    locked_at: datetime,
) -> None:
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        record = IdempotencyRecord(
            key=key,
            request_fingerprint="0" * 64,
            status=IdempotencyStatus.IN_PROGRESS,
            created_at=locked_at,
            expires_at=locked_at + timedelta(hours=24),
            locked_at=locked_at,
        )
        await uow.idempotency.insert_if_absent(record)
        await uow.commit()


class TestRecoverySweep:
    async def test_reconciles_when_provider_has_result(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        gateway = FakeGateway()
        await gateway.charge(
            GatewayChargeRequest(
                payment_id=uuid4(),
                amount=Decimal("10"),
                currency="USD",
                customer_id=uuid4(),
                idempotency_key="recover-1",
            ),
        )

        await _seed_stuck_record(
            session_factory,
            key="recover-1",
            locked_at=datetime.now(UTC) - timedelta(seconds=120),
        )

        sweeper = RecoverySweeper(
            _uow_factory(session_factory),
            gateway,
            stuck_after_seconds=60,
        )
        recovered = await sweeper.run_once()
        assert recovered == 1

        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            record = await uow.idempotency.get("recover-1")
        assert record is not None
        assert record.status is IdempotencyStatus.COMPLETED
        assert record.response_body is not None
        assert record.response_body["recovered"] is True
        assert record.response_body["status"] == "succeeded"

    async def test_leaves_record_when_provider_has_no_history(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        gateway = FakeGateway()
        await _seed_stuck_record(
            session_factory,
            key="recover-2",
            locked_at=datetime.now(UTC) - timedelta(seconds=120),
        )

        sweeper = RecoverySweeper(
            _uow_factory(session_factory),
            gateway,
            stuck_after_seconds=60,
        )
        recovered = await sweeper.run_once()
        assert recovered == 0

        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            record = await uow.idempotency.get("recover-2")
        assert record is not None
        assert record.status is IdempotencyStatus.IN_PROGRESS

    async def test_skips_records_within_grace_period(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        gateway = FakeGateway()
        await _seed_stuck_record(
            session_factory,
            key="recover-3",
            locked_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        sweeper = RecoverySweeper(
            _uow_factory(session_factory),
            gateway,
            stuck_after_seconds=60,
        )
        recovered = await sweeper.run_once()
        assert recovered == 0

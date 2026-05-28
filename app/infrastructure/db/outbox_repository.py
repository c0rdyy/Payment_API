from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.outbox_repository import OutboxRepository
from app.domain.outbox import OutboxEvent
from app.infrastructure.db.models import OutboxEventRow


def _to_domain(row: OutboxEventRow) -> OutboxEvent:
    return OutboxEvent(
        id=row.id,
        aggregate_id=row.aggregate_id,
        event_type=row.event_type,
        payload=dict(row.payload),
        created_at=row.created_at,
        processed_at=row.processed_at,
        attempts=row.attempts,
        last_error=row.last_error,
    )


def _to_row(event: OutboxEvent) -> OutboxEventRow:
    return OutboxEventRow(
        id=event.id,
        aggregate_id=event.aggregate_id,
        event_type=event.event_type,
        payload=dict(event.payload),
        created_at=event.created_at,
        processed_at=event.processed_at,
        attempts=event.attempts,
        last_error=event.last_error,
    )


class SqlAlchemyOutboxRepository(OutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OutboxEvent) -> None:
        self._session.add(_to_row(event))
        await self._session.flush()

    async def claim_batch(self, *, limit: int) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEventRow)
            .where(OutboxEventRow.processed_at.is_(None))
            .order_by(OutboxEventRow.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def mark_processed(self, event: OutboxEvent) -> None:
        event.mark_processed(now=datetime.now(UTC))
        await self._update(event)

    async def mark_failed(self, event: OutboxEvent) -> None:
        await self._update(event)

    async def count_unprocessed(self) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboxEventRow)
            .where(OutboxEventRow.processed_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def _update(self, event: OutboxEvent) -> None:
        await self._session.merge(_to_row(event))
        await self._session.flush()

"""Репозиторий для идемпотентности, реализованный на SQLAlchemy и PostgreSQL"""

from __future__ import annotations

import struct
from hashlib import sha256

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.idempotency_repository import IdempotencyRepository
from app.domain.idempotency import IdempotencyRecord, IdempotencyStatus
from app.infrastructure.db.models import IdempotencyKeyRow


def _to_domain(row: IdempotencyKeyRow) -> IdempotencyRecord:
    return IdempotencyRecord(
        key=row.key,
        request_fingerprint=row.request_fingerprint,
        status=row.status,
        created_at=row.created_at,
        expires_at=row.expires_at,
        locked_at=row.locked_at,
        response_status=row.response_status,
        response_body=dict(row.response_body) if row.response_body is not None else None,
        payment_id=row.payment_id,
    )


def _advisory_lock_id(key: str) -> int:
    """Построить 64-битный идентификатор для pg_advisory_xact_lock на основе ключа"""

    digest = sha256(key.encode("utf-8")).digest()
    lock_id: int = struct.unpack("!q", digest[:8])[0]
    return lock_id


class SqlAlchemyIdempotencyRepository(IdempotencyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_if_absent(self, record: IdempotencyRecord) -> bool:
        stmt = (
            pg_insert(IdempotencyKeyRow)
            .values(
                key=record.key,
                request_fingerprint=record.request_fingerprint,
                status=record.status,
                created_at=record.created_at,
                expires_at=record.expires_at,
                locked_at=record.locked_at,
            )
            .on_conflict_do_nothing(index_elements=["key"])
            .returning(IdempotencyKeyRow.key)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get(self, key: str) -> IdempotencyRecord | None:
        row = await self._session.get(IdempotencyKeyRow, key)
        return _to_domain(row) if row else None

    async def acquire_lock(self, key: str) -> None:
        lock_id = _advisory_lock_id(key)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )

    async def complete(self, record: IdempotencyRecord) -> None:
        stmt = (
            update(IdempotencyKeyRow)
            .where(IdempotencyKeyRow.key == record.key)
            .values(
                status=record.status,
                response_status=record.response_status,
                response_body=record.response_body,
                payment_id=record.payment_id,
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)

    async def list_stuck(
        self, *, older_than_seconds: int, limit: int = 100
    ) -> list[IdempotencyRecord]:
        threshold_sql = text("now() - make_interval(secs => :s)")
        stmt = (
            select(IdempotencyKeyRow)
            .where(IdempotencyKeyRow.status == IdempotencyStatus.IN_PROGRESS)
            .where(IdempotencyKeyRow.locked_at < threshold_sql.bindparams(s=older_than_seconds))
            .order_by(IdempotencyKeyRow.locked_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

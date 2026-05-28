from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.payment_repository import AttemptRecord, ConcurrencyError
from app.domain.money import Money
from app.domain.payment import Payment, PaymentStatus
from app.infrastructure.db.models import PaymentAttemptRow, PaymentRow


def _to_domain(row: PaymentRow) -> Payment:
    return Payment(
        id=row.id,
        customer_id=row.customer_id,
        money=Money(row.amount, row.currency),
        status=row.status,
        provider_reference=row.provider_reference,
        failure_reason=row.failure_reason,
        metadata=dict(row.payment_metadata),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_row(payment: Payment) -> PaymentRow:
    return PaymentRow(
        id=payment.id,
        customer_id=payment.customer_id,
        amount=payment.money.amount,
        currency=payment.money.currency,
        status=payment.status,
        provider_reference=payment.provider_reference,
        failure_reason=payment.failure_reason,
        payment_metadata=dict(payment.metadata),
        version=payment.version,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: UUID) -> Payment | None:
        row = await self._session.get(PaymentRow, payment_id)
        return _to_domain(row) if row else None

    async def add(self, payment: Payment) -> None:
        self._session.add(_to_row(payment))
        await self._session.flush()

    async def update(self, payment: Payment) -> None:
        expected_version = payment.version - 1
        stmt = (
            update(PaymentRow)
            .where(PaymentRow.id == payment.id, PaymentRow.version == expected_version)
            .values(
                status=payment.status,
                provider_reference=payment.provider_reference,
                failure_reason=payment.failure_reason,
                payment_metadata=dict(payment.metadata),
                version=payment.version,
                updated_at=payment.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        if not isinstance(result, CursorResult):
            raise RuntimeError("expected CursorResult from UPDATE")
        if result.rowcount == 0:
            raise ConcurrencyError(payment_id=payment.id, expected_version=expected_version)

    async def list_by_customer(self, customer_id: UUID, *, limit: int = 50) -> list[Payment]:
        stmt = (
            select(PaymentRow)
            .where(PaymentRow.customer_id == customer_id)
            .order_by(PaymentRow.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars()]

    async def get_status_counts(self) -> dict[PaymentStatus, int]:
        stmt = select(PaymentRow.status, func.count()).group_by(PaymentRow.status)
        result = await self._session.execute(stmt)
        return dict(result.tuples().all())

    async def record_attempt(self, attempt: AttemptRecord) -> None:
        self._session.add(
            PaymentAttemptRow(
                id=uuid4(),
                payment_id=attempt.payment_id,
                attempt_no=attempt.attempt_no,
                request_body=dict(attempt.request_body),
                response=dict(attempt.response) if attempt.response is not None else None,
                provider_status=attempt.provider_status,
                error=attempt.error,
                started_at=attempt.started_at,
                finished_at=attempt.finished_at,
            )
        )
        await self._session.flush()

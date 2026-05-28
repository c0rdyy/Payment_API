from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.ports.payment_gateway import GatewayChargeRequest, PaymentGateway
from app.application.ports.payment_repository import AttemptRecord
from app.application.ports.unit_of_work import UnitOfWork
from app.application.services.idempotency_service import IdempotentResponse
from app.core.metrics import PAYMENTS_TOTAL
from app.domain.money import Money
from app.domain.outbox import OutboxEvent
from app.domain.payment import Payment


@dataclass(frozen=True, slots=True)
class CreatePaymentCommand:
    customer_id: UUID
    amount: Decimal
    currency: str
    metadata: dict[str, str]
    idempotency_key: str


class CreatePayment:
    """Создать платеж, провести списание и вернуть ответ API

    Работает через адаптер PaymentGateway
    """

    def __init__(self, gateway: PaymentGateway) -> None:
        self._gateway = gateway

    async def __call__(
        self,
        command: CreatePaymentCommand,
        uow: UnitOfWork,
    ) -> IdempotentResponse:
        money = Money(command.amount, command.currency)
        payment = Payment.create(
            customer_id=command.customer_id,
            money=money,
            metadata=dict(command.metadata),
        )
        await uow.payments.add(payment)

        gateway_request = GatewayChargeRequest(
            payment_id=payment.id,
            amount=money.amount,
            currency=money.currency,
            customer_id=command.customer_id,
            idempotency_key=command.idempotency_key,
        )
        request_body: dict[str, Any] = {
            "payment_id": str(gateway_request.payment_id),
            "amount": str(gateway_request.amount),
            "currency": gateway_request.currency,
            "customer_id": str(gateway_request.customer_id),
        }

        started_at = datetime.now(UTC)
        try:
            result = await self._gateway.charge(gateway_request)
        except Exception as e:
            finished_at = datetime.now(UTC)
            await uow.payments.record_attempt(
                AttemptRecord(
                    payment_id=payment.id,
                    attempt_no=1,
                    request_body=request_body,
                    started_at=started_at,
                    finished_at=finished_at,
                    error=str(e),
                )
            )
            raise

        finished_at = datetime.now(UTC)
        await uow.payments.record_attempt(
            AttemptRecord(
                payment_id=payment.id,
                attempt_no=1,
                request_body=request_body,
                started_at=started_at,
                finished_at=finished_at,
                response={
                    "success": result.success,
                    "provider_reference": result.provider_reference,
                    "provider_status": result.provider_status,
                    "failure_reason": result.failure_reason,
                },
                provider_status=result.provider_status,
            )
        )

        if result.success:
            payment.mark_succeeded(provider_reference=result.provider_reference)
        else:
            payment.mark_failed(
                reason=result.failure_reason or "declined",
                provider_reference=result.provider_reference,
            )

        await uow.payments.update(payment)
        PAYMENTS_TOTAL.labels(status=payment.status.value).inc()

        event_type = (
            "payment.succeeded" if payment.status.value == "succeeded" else "payment.failed"
        )
        await uow.outbox.add(
            OutboxEvent.create(
                aggregate_id=payment.id,
                event_type=event_type,
                payload={
                    "payment_id": str(payment.id),
                    "customer_id": str(payment.customer_id),
                    "amount": str(money.amount),
                    "currency": money.currency,
                    "status": payment.status.value,
                    "provider_reference": payment.provider_reference,
                    "failure_reason": payment.failure_reason,
                },
                now=datetime.now(UTC),
            )
        )

        body: dict[str, Any] = {
            "id": str(payment.id),
            "customer_id": str(payment.customer_id),
            "amount": str(money.amount),
            "currency": money.currency,
            "status": payment.status.value,
            "provider_reference": payment.provider_reference,
            "failure_reason": payment.failure_reason,
            "created_at": payment.created_at.isoformat(),
            "updated_at": payment.updated_at.isoformat(),
        }
        return IdempotentResponse(status=201, body=body, payment_id=payment.id)

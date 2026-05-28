from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GatewayChargeRequest:
    payment_id: UUID
    amount: Decimal
    currency: str
    customer_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class GatewayChargeResult:
    """Результат попытки списания, который вернул провайдер"""

    success: bool
    provider_reference: str
    provider_status: str
    failure_reason: str | None = None


class PaymentGateway(Protocol):
    async def charge(self, request: GatewayChargeRequest) -> GatewayChargeResult: ...

    async def lookup(self, idempotency_key: str) -> GatewayChargeResult | None:
        """Проверка для обработки повторных запросов с тем же idempotency key,
        когда ответ на первый запрос потерялся по пути от провайдера к нам, и мы не знаем,
        было ли списание успешно или нет

        Возвращает None, если у провайдера нет записи по этому idempotency key
        """

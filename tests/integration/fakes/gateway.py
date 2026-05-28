from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from app.application.ports.payment_gateway import (
    GatewayChargeRequest,
    GatewayChargeResult,
    PaymentGateway,
)


@dataclass(slots=True)
class FakeGateway(PaymentGateway):
    mode: str = "success"
    delay_seconds: float = 0.0
    failure_reason: str = "card_declined"
    raises: BaseException | None = None
    calls: list[GatewayChargeRequest] = field(default_factory=list)
    response_factory: Callable[[GatewayChargeRequest], GatewayChargeResult] | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _results_by_key: dict[str, GatewayChargeResult] = field(default_factory=dict)

    async def charge(self, request: GatewayChargeRequest) -> GatewayChargeResult:
        async with self._lock:
            self.calls.append(request)
            cached = self._results_by_key.get(request.idempotency_key)
            if cached is not None:
                return cached
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.raises is not None:
            raise self.raises
        if self.response_factory is not None:
            result = self.response_factory(request)
        elif self.mode == "decline":
            result = GatewayChargeResult(
                success=False,
                provider_reference=f"ch_{uuid4().hex[:12]}",
                provider_status="declined",
                failure_reason=self.failure_reason,
            )
        else:
            result = GatewayChargeResult(
                success=True,
                provider_reference=f"ch_{uuid4().hex[:12]}",
                provider_status="approved",
            )
        async with self._lock:
            self._results_by_key[request.idempotency_key] = result
        return result

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def lookup(self, idempotency_key: str) -> GatewayChargeResult | None:
        for stored_key, stored_result in self._results_by_key.items():
            if stored_key == idempotency_key:
                return stored_result
        return None

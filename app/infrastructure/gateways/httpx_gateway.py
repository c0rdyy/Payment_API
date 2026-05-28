from __future__ import annotations

import structlog
from httpx import AsyncClient, HTTPStatusError, RequestError, Response
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.application.ports.payment_gateway import (
    GatewayChargeRequest,
    GatewayChargeResult,
    PaymentGateway,
)
from app.core.metrics import GATEWAY_ERRORS_TOTAL

log = structlog.get_logger()


class GatewayError(Exception):
    """Ошибка, когда gateway недоступен или вернул неразбираемый ответ"""


class HttpxPaymentGateway(PaymentGateway):
    def __init__(
        self,
        client: AsyncClient,
        *,
        retries: int = 2,
    ) -> None:
        self._client = client
        self._retries = retries

    async def charge(self, request: GatewayChargeRequest) -> GatewayChargeResult:
        payload = {
            "payment_id": str(request.payment_id),
            "amount": str(request.amount),
            "currency": request.currency,
            "customer_id": str(request.customer_id),
        }
        headers = {"Idempotency-Key": request.idempotency_key}

        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(self._retries + 1),
                wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0),
                retry=retry_if_exception_type((RequestError, _Retryable5xx)),
            ):
                with attempt:
                    response = await self._client.post(
                        "/charge",
                        json=payload,
                        headers=headers,
                    )
                    self._raise_for_retryable(response)
                    response.raise_for_status()
        except RequestError as e:
            log.warning("gateway.charge.network_error", error=str(e))
            GATEWAY_ERRORS_TOTAL.labels(category="network").inc()
            raise GatewayError(f"gateway unreachable: {e}") from e
        except _Retryable5xx as e:
            log.warning("gateway.charge.5xx_after_retries", status=e.status_code)
            GATEWAY_ERRORS_TOTAL.labels(category="5xx").inc()
            raise GatewayError(f"gateway 5xx after retries: {e.status_code}") from e
        except HTTPStatusError as e:
            log.warning("gateway.charge.http_error", status=e.response.status_code)
            GATEWAY_ERRORS_TOTAL.labels(category="4xx").inc()
            raise GatewayError(
                f"gateway returned {e.response.status_code}: {e.response.text}"
            ) from e
        except RetryError as e:
            GATEWAY_ERRORS_TOTAL.labels(category="retry_exhausted").inc()
            raise GatewayError(f"gateway retries exhausted: {e}") from e

        body = response.json()
        return GatewayChargeResult(
            success=bool(body["success"]),
            provider_reference=str(body["provider_reference"]),
            provider_status=str(body["provider_status"]),
            failure_reason=body.get("failure_reason"),
        )

    async def lookup(self, idempotency_key: str) -> GatewayChargeResult | None:
        try:
            response = await self._client.get(f"/charge/{idempotency_key}")
        except RequestError as e:
            raise GatewayError(f"gateway unreachable: {e}") from e
        if response.status_code == HTTP_NOT_FOUND:
            return None
        if HTTP_5XX_LOWER <= response.status_code < HTTP_5XX_UPPER:
            raise GatewayError(f"gateway 5xx during lookup: {response.status_code}")
        response.raise_for_status()
        body = response.json()
        return GatewayChargeResult(
            success=bool(body["success"]),
            provider_reference=str(body["provider_reference"]),
            provider_status=str(body["provider_status"]),
            failure_reason=body.get("failure_reason"),
        )

    @staticmethod
    def _raise_for_retryable(response: Response) -> None:
        if HTTP_5XX_LOWER <= response.status_code < HTTP_5XX_UPPER:
            raise _Retryable5xx(status_code=response.status_code)


HTTP_5XX_LOWER = 500
HTTP_5XX_UPPER = 600
HTTP_NOT_FOUND = 404


class _Retryable5xx(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"upstream {status_code}")
        self.status_code = status_code

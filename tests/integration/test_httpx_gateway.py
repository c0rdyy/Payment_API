from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from mock_provider.app import app as mock_app

from app.application.ports.payment_gateway import GatewayChargeRequest
from app.infrastructure.gateways.httpx_gateway import GatewayError, HttpxPaymentGateway


def _request(idempotency_key: str = "gw-test") -> GatewayChargeRequest:
    return GatewayChargeRequest(
        payment_id=uuid4(),
        amount=Decimal("10.00"),
        currency="USD",
        customer_id=uuid4(),
        idempotency_key=idempotency_key,
    )


@pytest.fixture
async def mock_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=mock_app)
    return httpx.AsyncClient(transport=transport, base_url="http://mock-provider")


class TestHappyPath:
    async def test_success_returns_approved(self, mock_client: httpx.AsyncClient) -> None:
        gateway = HttpxPaymentGateway(mock_client, retries=0)
        result = await gateway.charge(_request("gw-success-1"))
        assert result.success is True
        assert result.provider_status == "approved"
        assert result.provider_reference.startswith("ch_mock_")

    async def test_decline_returns_failure_reason(self, mock_client: httpx.AsyncClient) -> None:
        mock_client.headers["X-Mock-Mode"] = "decline"
        gateway = HttpxPaymentGateway(mock_client, retries=0)
        result = await gateway.charge(_request("gw-decline-1"))
        assert result.success is False
        assert result.failure_reason == "card_declined"


class TestFailures:
    async def test_5xx_raises_gateway_error(self, mock_client: httpx.AsyncClient) -> None:
        mock_client.headers["X-Mock-Mode"] = "5xx"
        gateway = HttpxPaymentGateway(mock_client, retries=2)
        with pytest.raises(GatewayError):
            await gateway.charge(_request("gw-5xx"))

    async def test_network_error_raises_gateway_error(self) -> None:
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:1",
            timeout=0.1,
        ) as broken_client:
            gateway = HttpxPaymentGateway(broken_client, retries=1)
            with pytest.raises(GatewayError):
                await gateway.charge(_request("gw-network"))


class TestProviderIdempotency:
    async def test_repeat_with_same_idempotency_key_returns_same_reference(
        self,
        mock_client: httpx.AsyncClient,
    ) -> None:
        gateway = HttpxPaymentGateway(mock_client, retries=0)
        first = await gateway.charge(_request("gw-idem-shared"))
        second = await gateway.charge(_request("gw-idem-shared"))
        assert first.provider_reference == second.provider_reference

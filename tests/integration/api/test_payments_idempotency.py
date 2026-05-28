from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.integration.api.conftest import auth_headers
from tests.integration.fakes.gateway import FakeGateway

pytestmark = pytest.mark.integration


def _payment_body(amount: str = "12.50", currency: str = "USD") -> dict[str, object]:
    return {
        "customer_id": str(uuid4()),
        "amount": amount,
        "currency": currency,
        "metadata": {"order_id": "order_1"},
    }


class TestHappyPath:
    async def test_first_request_creates_payment(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, gateway, _ = http_app
        body = _payment_body()
        response = await client.post(
            "/v1/payments",
            headers=auth_headers("idem-1"),
            json=body,
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "succeeded"
        assert payload["currency"] == "USD"
        assert payload["amount"] == "12.5000"
        assert payload["provider_reference"]
        assert gateway.call_count == 1

    async def test_repeat_same_request_returns_cached(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, gateway, _ = http_app
        body = _payment_body()
        first = await client.post("/v1/payments", headers=auth_headers("idem-2"), json=body)
        second = await client.post("/v1/payments", headers=auth_headers("idem-2"), json=body)
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        assert gateway.call_count == 1


class TestKeyMisuse:
    async def test_same_key_different_body_returns_422(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, gateway, _ = http_app
        first = await client.post(
            "/v1/payments",
            headers=auth_headers("idem-3"),
            json=_payment_body(amount="10.00"),
        )
        assert first.status_code == 201
        second = await client.post(
            "/v1/payments",
            headers=auth_headers("idem-3"),
            json=_payment_body(amount="20.00"),
        )
        assert second.status_code == 422
        assert "different request body" in second.json()["detail"]
        assert gateway.call_count == 1

    async def test_missing_idempotency_key_returns_400(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, _, _ = http_app
        response = await client.post(
            "/v1/payments",
            headers={"X-API-Key": "test-api-key-1234", "Content-Type": "application/json"},
            json=_payment_body(),
        )
        assert response.status_code == 400

    async def test_missing_api_key_returns_401(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, _, _ = http_app
        response = await client.post(
            "/v1/payments",
            headers={"Idempotency-Key": "idem-noauth", "Content-Type": "application/json"},
            json=_payment_body(),
        )
        assert response.status_code == 401


class TestConcurrency:
    async def test_concurrent_same_key_creates_one_payment(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, gateway, _ = http_app

        gateway.delay_seconds = 0.2
        body = _payment_body()
        headers = auth_headers("idem-concurrent")

        coros = [client.post("/v1/payments", headers=headers, json=body) for _ in range(10)]
        results = await asyncio.gather(*coros)

        statuses = {r.status_code for r in results}
        assert statuses == {201}, f"unexpected statuses: {statuses}"
        ids = {r.json()["id"] for r in results}
        assert len(ids) == 1, f"expected one payment id, got {ids}"

        assert gateway.call_count == 1, f"gateway called {gateway.call_count} times"


class TestProviderOutcomes:
    async def test_decline_recorded_as_failed_payment(
        self,
        http_app: tuple[AsyncClient, FakeGateway, object],
    ) -> None:
        client, gateway, _ = http_app
        gateway.mode = "decline"
        gateway.failure_reason = "insufficient_funds"

        response = await client.post(
            "/v1/payments",
            headers=auth_headers("idem-decline"),
            json=_payment_body(),
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["failure_reason"] == "insufficient_funds"

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import deps as api_deps
from app.core.config import get_settings
from app.main import create_app
from tests.integration.fakes.gateway import FakeGateway


@pytest.fixture
async def http_app(
    database_url: str,
    session_factory: async_sessionmaker,
) -> AsyncIterator[tuple[AsyncClient, FakeGateway, object]]:
    """Поднимает тестовый экземпляр приложения с фейковым gateway
    и возвращает HTTP-клиент для него"""
    os.environ["DATABASE_URL"] = database_url
    os.environ["APP_API_KEY"] = "test-api-key-1234"
    os.environ["PAYMENT_GATEWAY_URL"] = "http://mock-provider:9000"
    get_settings.cache_clear()

    app = create_app()
    fake_gateway = FakeGateway()
    app.state.payment_gateway = fake_gateway

    app.state.session_factory = session_factory

    app.dependency_overrides[api_deps.get_session_factory] = lambda: session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake_gateway, app


def auth_headers(idempotency_key: str) -> dict[str, str]:
    return {
        "X-API-Key": "test-api-key-1234",
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/json",
    }

from __future__ import annotations

import os

import pytest

from app.core.config import get_settings


def pytest_configure(config: pytest.Config) -> None:
    del config
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("APP_API_KEY", "test-api-key-1234")
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://payments:payments@localhost:5432/payments_test",
    )
    os.environ.setdefault("PAYMENT_GATEWAY_URL", "http://mock-provider:9000")

    get_settings.cache_clear()

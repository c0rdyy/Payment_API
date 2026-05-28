"""Настройки приложения"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    # Приложение
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_debug: bool = False
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_api_key: str = Field(min_length=8)

    # БД
    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: RedisDsn | None = None

    payment_gateway_url: str
    payment_gateway_timeout_seconds: float = 5.0
    payment_gateway_retries: int = 2

    idempotency_key_ttl_hours: int = 24
    idempotency_inprogress_timeout_seconds: int = 30

    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "payments-api"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

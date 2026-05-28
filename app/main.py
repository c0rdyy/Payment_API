from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI

from app import __version__
from app.api.middleware.request_id import RequestIdMiddleware
from app.api.v1.payments import router as payments_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.metrics import PrometheusMiddleware, metrics_endpoint
from app.core.telemetry import configure_tracing
from app.infrastructure.gateways.httpx_gateway import HttpxPaymentGateway


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        level=settings.app_log_level,
        json_format=settings.app_env != "local",
    )
    log = structlog.get_logger()
    log.info("app.startup", env=settings.app_env, version=__version__)

    http_client = httpx.AsyncClient(
        base_url=settings.payment_gateway_url,
        timeout=settings.payment_gateway_timeout_seconds,
    )
    app.state.gateway_http_client = http_client
    if not getattr(app.state, "payment_gateway", None):
        app.state.payment_gateway = HttpxPaymentGateway(
            http_client,
            retries=settings.payment_gateway_retries,
        )

    try:
        yield
    finally:
        await http_client.aclose()
        log.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Payments API",
        version=__version__,
        description="Payment API with idempotency",
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(payments_router)
    app.add_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    configure_tracing(
        app,
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    return app

"""Prometheus-метрики"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests, partitioned by method, route, and status code.",
    labelnames=("method", "route", "status_code"),
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, partitioned by method and route.",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

PAYMENTS_TOTAL = Counter(
    "payments_total",
    "Total payments created, by terminal status.",
    labelnames=("status",),
)

IDEMPOTENCY_HITS_TOTAL = Counter(
    "idempotency_hits_total",
    "Idempotency lookups, by outcome (claimed=first request, cached=replay, conflict=in_flight, mismatch=fingerprint).",
    labelnames=("outcome",),
)

GATEWAY_ERRORS_TOTAL = Counter(
    "gateway_errors_total",
    "Errors talking to the payment gateway, by category.",
    labelnames=("category",),
)

OUTBOX_UNPROCESSED = Gauge(
    "outbox_unprocessed_events",
    "Current count of outbox events awaiting dispatch.",
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        method = request.method
        start = perf_counter()
        response = await call_next(request)
        duration = perf_counter() - start

        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)

        HTTP_REQUEST_DURATION.labels(method=method, route=route_path).observe(duration)
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            route=route_path,
            status_code=str(response.status_code),
        ).inc()
        return response


async def metrics_endpoint(request: Request) -> Response:
    del request
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

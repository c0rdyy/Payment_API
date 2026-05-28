"""Mock-платежный провайдер

Заменяет реальные платежные сервисы во время разработки и тестов.
Позволяет имитировать разные сценарии взаимодействия с провайдером, включая сбои и задержки.

Режимы:
    1. success (по умолчанию): всегда успешные платежи
    2. decline: платежи отклоняются с типичной причиной отказа
    3. 5xx: провайдер недоступен, возвращает 503
    4. slow: провайдер отвечает с задержкой (настраивается через MOCK_SLOW_DELAY_MS)
    5. timeout: провайдер не отвечает в течение длительного времени (настраивается через MOCK_TIMEOUT_DELAY_MS)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

DEFAULT_MODE = os.getenv("MOCK_DEFAULT_MODE", "success")
SUCCESS_DELAY_MS = int(os.getenv("MOCK_SUCCESS_DELAY_MS", "0"))
SLOW_DELAY_MS = int(os.getenv("MOCK_SLOW_DELAY_MS", "2000"))
TIMEOUT_DELAY_MS = int(os.getenv("MOCK_TIMEOUT_DELAY_MS", "30000"))


class ChargeRequest(BaseModel):
    payment_id: str
    amount: str
    currency: str = Field(min_length=3, max_length=3)
    customer_id: str


class ChargeResponse(BaseModel):
    success: bool
    provider_reference: str
    provider_status: Literal["approved", "declined"]
    failure_reason: str | None = None


_cache: dict[str, ChargeResponse] = {}
_lock = asyncio.Lock()

app = FastAPI(title="Mock Payment Provider", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/charge", response_model=ChargeResponse, status_code=status.HTTP_200_OK)
async def charge(
    body: ChargeRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    mode: Annotated[str | None, Header(alias="X-Mock-Mode")] = None,
) -> ChargeResponse:
    async with _lock:
        if idempotency_key in _cache:
            return _cache[idempotency_key]

    effective_mode = (mode or DEFAULT_MODE).lower()

    if effective_mode == "5xx":
        raise HTTPException(status_code=503, detail="provider unavailable")
    if effective_mode == "timeout":
        await asyncio.sleep(TIMEOUT_DELAY_MS / 1000)
    if effective_mode == "slow":
        await asyncio.sleep(SLOW_DELAY_MS / 1000)
    if effective_mode == "success" and SUCCESS_DELAY_MS:
        await asyncio.sleep(SUCCESS_DELAY_MS / 1000)

    if effective_mode == "decline":
        response = ChargeResponse(
            success=False,
            provider_reference=f"ch_mock_{uuid.uuid4().hex[:12]}",
            provider_status="declined",
            failure_reason="card_declined",
        )
    else:
        response = ChargeResponse(
            success=True,
            provider_reference=f"ch_mock_{uuid.uuid4().hex[:12]}",
            provider_status="approved",
        )

    async with _lock:
        _cache[idempotency_key] = response
    return response


@app.get("/charge/{idempotency_key}")
async def charge_status(idempotency_key: str) -> ChargeResponse:
    if idempotency_key not in _cache:
        raise HTTPException(status_code=404, detail="unknown idempotency key")
    return _cache[idempotency_key]

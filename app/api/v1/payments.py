from __future__ import annotations

from typing import Annotated, Any

import orjson
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    get_create_payment,
    get_idempotency_service,
    require_api_key,
    require_idempotency_key,
)
from app.api.v1.schemas import CreatePaymentRequest, PaymentResponse
from app.application.services.create_payment import CreatePayment, CreatePaymentCommand
from app.application.services.idempotency_service import (
    IdempotencyService,
    IdempotentResponse,
)
from app.domain.exceptions import (
    DomainError,
    FingerprintMismatch,
    IdempotencyConflict,
    InvalidMoney,
)
from app.infrastructure.idempotency.fingerprint import fingerprint

router = APIRouter(prefix="/v1/payments", tags=["payments"])
log = structlog.get_logger()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentResponse,
    dependencies=[Depends(require_api_key)],
    summary="Create a payment",
    description=(
        "Create a payment with idempotency guarantees.\n\n"
        "The `Idempotency-Key` header is **required** and must be ≤255 ASCII printable "
        "characters. Repeating the request with the same key and the same body returns "
        "the cached response (status, body, payment id) without re-charging the gateway. "
        "Repeating the same key with a different body returns 422."
    ),
    responses={
        400: {"description": "Idempotency-Key missing or invalid"},
        401: {"description": "API key missing or invalid"},
        409: {"description": "Idempotency key already in flight (or recovered failure)"},
        422: {"description": "Idempotency key reused with different body, or invalid amount"},
    },
)
async def create_payment_endpoint(
    body: CreatePaymentRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
    create_payment: Annotated[CreatePayment, Depends(get_create_payment)],
) -> Response:
    request_fingerprint = _fingerprint_request(body)

    log.info(
        "payments.create.received",
        idempotency_key=idempotency_key,
        customer_id=str(body.customer_id),
        request_fingerprint=request_fingerprint,
    )

    command = CreatePaymentCommand(
        customer_id=body.customer_id,
        amount=body.amount,
        currency=body.currency,
        metadata=dict(body.metadata),
        idempotency_key=idempotency_key,
    )

    try:
        response = await idempotency.execute(
            key=idempotency_key,
            request_fingerprint=request_fingerprint,
            action=lambda uow: create_payment(command, uow),
        )
    except FingerprintMismatch as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except IdempotencyConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except InvalidMoney as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except DomainError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    return _to_http_response(response)


def _fingerprint_request(body: CreatePaymentRequest) -> str:
    payload: dict[str, Any] = {
        "customer_id": str(body.customer_id),
        "amount": body.amount,
        "currency": body.currency,
        "metadata": dict(body.metadata),
    }
    return fingerprint(payload)


def _to_http_response(response: IdempotentResponse) -> Response:
    return JSONResponse(
        status_code=response.status,
        content=orjson.loads(orjson.dumps(response.body)),
    )

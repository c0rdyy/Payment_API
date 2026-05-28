"""Pydantic-схемы запросов и ответов для Payments API"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreatePaymentRequest(BaseModel):
    """Тело входящего POST /v1/payments"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "customer_id": "1e8a4d6e-4f59-4c2f-8a48-9e7d6f1d4af2",
                    "amount": "199.99",
                    "currency": "USD",
                    "metadata": {"order_id": "ORD-42"},
                }
            ]
        }
    )

    customer_id: UUID
    amount: Annotated[Decimal, Field(gt=0)]
    currency: Annotated[str, Field(min_length=3, max_length=3)]
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _uppercase_currency(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be alphabetic")
        if v != v.upper():
            raise ValueError("currency must be uppercase")
        return v


class PaymentResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "7c7e0d68-2a18-4dde-9c6c-0a93de1ec1d9",
                    "customer_id": "1e8a4d6e-4f59-4c2f-8a48-9e7d6f1d4af2",
                    "amount": "199.99",
                    "currency": "USD",
                    "status": "succeeded",
                    "provider_reference": "ch_3PqrSt12abCdEf",
                    "failure_reason": None,
                    "created_at": "2026-05-21T10:11:12.000000+00:00",
                    "updated_at": "2026-05-21T10:11:12.450000+00:00",
                }
            ]
        }
    )

    id: UUID
    customer_id: UUID
    amount: Decimal
    currency: str
    status: str
    provider_reference: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    code: str
    message: str

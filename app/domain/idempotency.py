from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class IdempotencyRecord:
    key: str
    request_fingerprint: str
    status: IdempotencyStatus
    created_at: datetime
    expires_at: datetime
    locked_at: datetime
    response_status: int | None = None
    response_body: dict[str, Any] | None = None
    payment_id: UUID | None = None

    @classmethod
    def start(
        cls,
        *,
        key: str,
        request_fingerprint: str,
        ttl: timedelta,
    ) -> IdempotencyRecord:
        now = _utcnow()
        return cls(
            key=key,
            request_fingerprint=request_fingerprint,
            status=IdempotencyStatus.IN_PROGRESS,
            created_at=now,
            expires_at=now + ttl,
            locked_at=now,
        )

    def matches_fingerprint(self, fingerprint: str) -> bool:
        return self.request_fingerprint == fingerprint

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or _utcnow()) >= self.expires_at

    def is_stuck(self, *, timeout: timedelta, now: datetime | None = None) -> bool:
        if self.status is not IdempotencyStatus.IN_PROGRESS:
            return False
        return (now or _utcnow()) - self.locked_at >= timeout

    def complete(
        self,
        *,
        response_status: int,
        response_body: dict[str, Any],
        payment_id: UUID | None,
    ) -> None:
        self.status = IdempotencyStatus.COMPLETED
        self.response_status = response_status
        self.response_body = response_body
        self.payment_id = payment_id

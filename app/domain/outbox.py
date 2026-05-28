from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class OutboxEvent:
    id: UUID
    aggregate_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    processed_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> OutboxEvent:
        return cls(
            id=uuid4(),
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=dict(payload),
            created_at=now,
        )

    def mark_processed(self, *, now: datetime) -> None:
        self.processed_at = now

    def mark_failed(self, *, error: str) -> None:
        self.attempts += 1
        self.last_error = error[:1024]


EventId = UUID

__all__ = ["EventId", "OutboxEvent"]

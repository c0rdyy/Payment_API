"""Базовая миграция

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-21 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Пустая база"""


def downgrade() -> None:
    """Откатывать нечего"""

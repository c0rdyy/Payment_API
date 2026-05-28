"""Таблица idempotency_keys

Revision ID: 0003_idempotency
Revises: 0002_payments
Create Date: 2026-05-21 00:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_idempotency"
down_revision: str | Sequence[str] | None = "0002_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    idempotency_status = postgresql.ENUM(
        "in_progress",
        "completed",
        name="idempotency_status",
        create_type=True,
    )
    idempotency_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="idempotency_status", create_type=False),
            nullable=False,
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column(
            "response_body",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="ck_idempotency_keys_fingerprint_length",
        ),
    )
    # Cheap to scan, used by the recovery sweeper.
    op.create_index(
        "ix_idempotency_keys_in_progress_locked_at",
        "idempotency_keys",
        ["locked_at"],
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    # Used by the cleanup job that drops expired completed keys.
    op.create_index(
        "ix_idempotency_keys_completed_expires_at",
        "idempotency_keys",
        ["expires_at"],
        postgresql_where=sa.text("status = 'completed'"),
    )
    op.create_index(
        "ix_idempotency_keys_payment_id",
        "idempotency_keys",
        ["payment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_payment_id", table_name="idempotency_keys")
    op.drop_index(
        "ix_idempotency_keys_completed_expires_at",
        table_name="idempotency_keys",
    )
    op.drop_index(
        "ix_idempotency_keys_in_progress_locked_at",
        table_name="idempotency_keys",
    )
    op.drop_table("idempotency_keys")
    sa.Enum(name="idempotency_status").drop(op.get_bind(), checkfirst=True)

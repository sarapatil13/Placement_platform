"""add revoked_refresh_tokens

Revision ID: 3f9a2c4e8b1d
Revises: 264a0e98b34f
Create Date: 2026-09-28 22:20:00.000000

Server-side denylist for refresh-token rotation/logout/replay protection.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3f9a2c4e8b1d"
down_revision = "264a0e98b34f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_refresh_tokens",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_revoked_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_revoked_refresh_tokens")),
        sa.UniqueConstraint(
            "jti_hash", name=op.f("uq_revoked_refresh_tokens_jti_hash")
        ),
    )
    op.create_index(
        op.f("ix_revoked_refresh_tokens_expires_at"),
        "revoked_refresh_tokens",
        ["expires_at"],
    )
    op.create_index(
        op.f("ix_revoked_refresh_tokens_user_id"),
        "revoked_refresh_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_revoked_refresh_tokens_user_id"),
        table_name="revoked_refresh_tokens",
    )
    op.drop_index(
        op.f("ix_revoked_refresh_tokens_expires_at"),
        table_name="revoked_refresh_tokens",
    )
    op.drop_table("revoked_refresh_tokens")
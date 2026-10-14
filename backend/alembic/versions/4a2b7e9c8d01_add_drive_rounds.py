"""add drive_rounds

Revision ID: 4a2b7e9c8d01
Revises: 3f9a2c4e8b1d
Create Date: 2026-09-29 00:00:00.000000

Add drive_rounds table for company-specific recruitment rounds.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "4a2b7e9c8d01"
down_revision = "3f9a2c4e8b1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drive_rounds",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("institution_id", sa.String(length=32), nullable=False),
        sa.Column("drive_id", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("round_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_drive_rounds_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["drive_id"],
            ["placement_drives.id"],
            name=op.f("fk_drive_rounds_drive_id_placement_drives"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drive_rounds")),
        sa.UniqueConstraint(
            "drive_id",
            "position",
            name=op.f("uq_drive_rounds_drive_id_position"),
        ),
    )
    op.create_index(
        op.f("ix_drive_rounds_drive_id"),
        "drive_rounds",
        ["drive_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_drive_rounds_drive_id"), table_name="drive_rounds")
    op.drop_table("drive_rounds")

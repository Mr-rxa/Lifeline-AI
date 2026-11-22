"""add police units

Revision ID: f8c2d4e1a9b3
Revises: ae6a75abfe0b
Create Date: 2026-11-22
"""

from alembic import op
import sqlalchemy as sa


revision = "f8c2d4e1a9b3"
down_revision = "ae6a75abfe0b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "police_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unit_number", sa.String(length=30), nullable=False),
        sa.Column("station_name", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("officer_id", sa.Integer(), nullable=True),
        sa.Column("last_lat", sa.Float(), nullable=True),
        sa.Column("last_lon", sa.Float(), nullable=True),
        sa.Column("last_update", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["officer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_number"),
    )


def downgrade() -> None:
    op.drop_table("police_units")

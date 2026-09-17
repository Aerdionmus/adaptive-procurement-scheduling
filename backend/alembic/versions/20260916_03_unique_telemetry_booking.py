"""enforce one telemetry row per booking

Revision ID: 20260916_03
Revises: 20260916_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_03"
down_revision = "20260916_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_procurement_telemetry_booking_id",
        "procurement_telemetry",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("booking_id IS NOT NULL"),
        sqlite_where=sa.text("booking_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_procurement_telemetry_booking_id",
        table_name="procurement_telemetry",
    )

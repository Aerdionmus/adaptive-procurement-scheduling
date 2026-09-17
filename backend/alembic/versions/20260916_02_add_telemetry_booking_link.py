"""link operational telemetry to bookings

Revision ID: 20260916_02
Revises: 20260916_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_02"
down_revision = "20260916_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("procurement_telemetry") as batch_op:
        batch_op.add_column(sa.Column("booking_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_procurement_telemetry_booking_id",
            "bookings",
            ["booking_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_procurement_telemetry_booking_id",
            ["booking_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("procurement_telemetry") as batch_op:
        batch_op.drop_index("ix_procurement_telemetry_booking_id")
        batch_op.drop_constraint(
            "fk_procurement_telemetry_booking_id",
            type_="foreignkey",
        )
        batch_op.drop_column("booking_id")

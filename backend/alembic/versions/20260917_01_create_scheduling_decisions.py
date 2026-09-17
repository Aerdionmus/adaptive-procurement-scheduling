"""create append-only scheduling decisions

Revision ID: 20260917_01
Revises: 20260916_04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_01"
down_revision = "20260916_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduling_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("centre_id", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduling_status", sa.String(length=30), nullable=False),
        sa.Column("recommendation", sa.String(length=50), nullable=False),
        sa.Column("estimated_completion_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_wait_minutes", sa.Numeric(10, 2), nullable=False),
        sa.Column("farmers_ahead", sa.Integer(), nullable=False),
        sa.Column("prediction_status", sa.String(length=30), nullable=True),
        sa.Column("prediction_provenance", sa.String(length=50), nullable=False),
        sa.Column("recommended_slot_id", sa.Integer(), nullable=True),
        sa.Column("recommended_centre_id", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("decision_version", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["centre_id"], ["procurement_centres.id"]),
        sa.ForeignKeyConstraint(["slot_id"], ["procurement_slots.id"]),
        sa.ForeignKeyConstraint(["recommended_slot_id"], ["procurement_slots.id"]),
        sa.ForeignKeyConstraint(["recommended_centre_id"], ["procurement_centres.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduling_decisions_booking_id", "scheduling_decisions", ["booking_id"])
    op.create_index("ix_scheduling_decisions_centre_id", "scheduling_decisions", ["centre_id"])
    op.create_index("ix_scheduling_decisions_evaluated_at", "scheduling_decisions", ["evaluated_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduling_decisions_evaluated_at", table_name="scheduling_decisions")
    op.drop_index("ix_scheduling_decisions_centre_id", table_name="scheduling_decisions")
    op.drop_index("ix_scheduling_decisions_booking_id", table_name="scheduling_decisions")
    op.drop_table("scheduling_decisions")

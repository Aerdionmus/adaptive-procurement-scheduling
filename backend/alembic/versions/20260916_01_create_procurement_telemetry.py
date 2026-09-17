"""create operational procurement telemetry table

Revision ID: 20260916_01
Revises: 20260908_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_01"
down_revision = "20260908_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_telemetry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_id", sa.String(length=100), nullable=False),
        sa.Column("centre_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_slot", sa.String(length=100), nullable=True),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_size_at_arrival", sa.Integer(), nullable=True),
        sa.Column("registration_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unloading_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unloading_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weighment_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weighment_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("documentation_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("documentation_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resource_state", sa.JSON(), nullable=True),
        sa.Column("no_show", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cancellation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("completion_status", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["centre_id"], ["procurement_centres.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_procurement_telemetry_lot_id", "procurement_telemetry", ["lot_id"])
    op.create_index("ix_procurement_telemetry_centre_id", "procurement_telemetry", ["centre_id"])


def downgrade() -> None:
    op.drop_index("ix_procurement_telemetry_centre_id", table_name="procurement_telemetry")
    op.drop_index("ix_procurement_telemetry_lot_id", table_name="procurement_telemetry")
    op.drop_table("procurement_telemetry")

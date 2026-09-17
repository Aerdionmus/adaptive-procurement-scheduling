"""create provider-neutral notification intents

Revision ID: 20260917_02
Revises: 20260917_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_02"
down_revision = "20260917_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_intents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("centre_id", sa.Integer(), nullable=False),
        sa.Column("farmer_id", sa.Integer(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "FARMER_SLOT_AT_RISK",
                "FARMER_NEW_SLOT_PROPOSED",
                "FARMER_ALTERNATE_CENTRE_PROPOSED",
                name="notification_intent_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum("SMS", "WHATSAPP", "IVR", "IN_APP", name="notification_intent_channel"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "DELIVERED", "FAILED", name="notification_intent_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["scheduling_decisions.id"]),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["centre_id"], ["procurement_centres.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_id",
            "notification_type",
            "channel",
            name="uq_notification_intent_decision_type_channel",
        ),
    )
    op.create_index("ix_notification_intents_decision_id", "notification_intents", ["decision_id"])
    op.create_index("ix_notification_intents_booking_id", "notification_intents", ["booking_id"])
    op.create_index("ix_notification_intents_centre_id", "notification_intents", ["centre_id"])
    op.create_index("ix_notification_intents_farmer_id", "notification_intents", ["farmer_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_intents_farmer_id", table_name="notification_intents")
    op.drop_index("ix_notification_intents_centre_id", table_name="notification_intents")
    op.drop_index("ix_notification_intents_booking_id", table_name="notification_intents")
    op.drop_index("ix_notification_intents_decision_id", table_name="notification_intents")
    op.drop_table("notification_intents")

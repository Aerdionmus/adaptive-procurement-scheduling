"""add notification processing state timestamp

Revision ID: 20260917_04
Revises: 20260917_03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_04"
down_revision = "20260917_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_intents") as batch_op:
        batch_op.add_column(
            sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("notification_intents") as batch_op:
        batch_op.drop_column("processing_started_at")

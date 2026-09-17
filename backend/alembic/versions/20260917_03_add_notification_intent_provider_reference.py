"""add generic notification delivery reference

Revision ID: 20260917_03
Revises: 20260917_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_03"
down_revision = "20260917_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_intents",
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_intents", "provider_reference")

"""add explicit telemetry provenance

Revision ID: 20260916_04
Revises: 20260916_03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_04"
down_revision = "20260916_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("procurement_telemetry") as batch_op:
        batch_op.add_column(
            sa.Column(
                "provenance",
                sa.String(length=20),
                nullable=False,
                server_default="LEGACY",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("procurement_telemetry") as batch_op:
        batch_op.drop_column("provenance")

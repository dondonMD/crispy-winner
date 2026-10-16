"""Separate manual journal state and bounded prospective research work."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
    )
    op.create_index("ix_manual_positions_mode", "manual_positions", ["mode"])
    op.create_index("ix_manual_positions_status", "manual_positions", ["status"])
    op.create_index("ix_manual_recent", "manual_positions", ["mode", "status", "updated_at"])
    op.create_table(
        "opportunity_pending",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payload", sa.Text, nullable=False),
    )


def downgrade():
    op.drop_table("opportunity_pending")
    op.drop_table("manual_positions")

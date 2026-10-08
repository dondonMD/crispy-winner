"""Restart-safe bounded deduplication identities."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_identities",
        sa.Column("event_id", sa.String(150), primary_key=True),
        sa.Column("ts", sa.Float, nullable=False),
    )
    op.create_index("ix_event_identities_ts", "event_identities", ["ts"])


def downgrade():
    op.drop_table("event_identities")

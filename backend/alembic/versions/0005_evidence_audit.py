"""Lossless context references and bounded per-session operational receipts."""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TABLE evidence_contexts (digest TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    op.execute("CREATE TABLE evidence_runs (session TEXT PRIMARY KEY, payload TEXT NOT NULL)")


def downgrade():
    raise RuntimeError("Evidence audit records must not be removed destructively")

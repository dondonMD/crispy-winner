"""Immutable prospective manifests, enrollment/outcomes and restart-safe work."""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        "CREATE TABLE prospective_cohorts (cohort_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, digest TEXT NOT NULL)",
        """CREATE TABLE prospective_enrollments (
            cohort_id TEXT NOT NULL REFERENCES prospective_cohorts(cohort_id), signal_id INTEGER NOT NULL,
            session TEXT NOT NULL, mint TEXT NOT NULL, ts REAL NOT NULL, primary_sample INTEGER NOT NULL,
            snapshot TEXT NOT NULL, enrolled_at REAL NOT NULL, PRIMARY KEY(cohort_id, signal_id))""",
        """CREATE UNIQUE INDEX prospective_primary ON prospective_enrollments(cohort_id, session, mint)
            WHERE primary_sample=1""",
        """CREATE TABLE prospective_outcomes (cohort_id TEXT NOT NULL, signal_id INTEGER NOT NULL,
            horizon INTEGER NOT NULL, ts REAL NOT NULL, payload TEXT NOT NULL, recorded_at REAL NOT NULL,
            PRIMARY KEY(cohort_id, signal_id, horizon), FOREIGN KEY(cohort_id, signal_id)
            REFERENCES prospective_enrollments(cohort_id, signal_id))""",
        """CREATE TABLE prospective_pending (cohort_id TEXT NOT NULL, signal_id INTEGER NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(cohort_id, signal_id), FOREIGN KEY(cohort_id, signal_id)
            REFERENCES prospective_enrollments(cohort_id, signal_id))""",
        """CREATE TABLE prospective_sessions (cohort_id TEXT NOT NULL REFERENCES prospective_cohorts(cohort_id),
            session TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(cohort_id, session))""",
    ]
    for sql in statements:
        op.execute(sql)
    for table in ("prospective_cohorts", "prospective_enrollments", "prospective_outcomes"):
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                       "BEGIN SELECT RAISE(ABORT, 'Frozen prospective ledger'); END")


def downgrade():
    # Immutable research is deliberately not destroyed by migration rollback.
    raise RuntimeError("Prospective research ledger cannot be downgraded destructively")

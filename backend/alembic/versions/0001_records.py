"""Compact indexed journal; paper and strategy records protected from retention."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('records', sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('kind', sa.String(32), nullable=False),
                    sa.Column('mint', sa.String(64), nullable=False),
                    sa.Column('ts', sa.Float, nullable=False),
                    sa.Column('session', sa.String(40), nullable=False),
                    sa.Column('payload', sa.Text, nullable=False))
    op.create_index('ix_kind_ts', 'records', ['kind', 'ts'])
    op.create_index('ix_mint_ts', 'records', ['mint', 'ts'])
    op.create_index('ix_session_kind', 'records', ['session', 'kind'])


def downgrade():
    op.drop_table('records')

"""auto-enrich prefs + partial_enrich run type

Revision ID: v9_auto_enrich
Revises: v8_brightdata_source
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'v9_auto_enrich'
down_revision = 'v8_brightdata_source'
branch_labels = None
depends_on = None


def upgrade():
    # Opt-in daily auto-enrich of high-scoring partial-JD jobs (default OFF).
    op.add_column('user_preferences',
                  sa.Column('auto_enrich_partials', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('user_preferences',
                  sa.Column('auto_enrich_threshold', sa.Integer(), nullable=False, server_default='70'))
    # New RunType for the cron's run-log entry (not USED in this migration → safe in-transaction).
    op.execute("ALTER TYPE runtype ADD VALUE IF NOT EXISTS 'partial_enrich'")


def downgrade():
    op.drop_column('user_preferences', 'auto_enrich_threshold')
    op.drop_column('user_preferences', 'auto_enrich_partials')
    # NB: Postgres can't DROP an enum value; 'partial_enrich' stays on runtype (harmless).

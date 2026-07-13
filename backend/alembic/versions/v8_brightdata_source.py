"""Bright Data source: jobsource enum + credentials token + feed provider_config

Revision ID: v8_brightdata_source
Revises: v7_dedup_key_unique
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'v8_brightdata_source'
down_revision = 'v7_dedup_key_unique'
branch_labels = None
depends_on = None


def upgrade():
    # New enum value — not USED in this migration, so safe in-transaction (PG 12+),
    # mirroring v3_gmail_job_alerts.
    op.execute("ALTER TYPE jobsource ADD VALUE IF NOT EXISTS 'brightdata'")
    # BYOK token (mirrors the apify_token columns).
    op.add_column('user_credentials', sa.Column('brightdata_token_enc', sa.Text(), nullable=True))
    op.add_column('user_credentials',
                  sa.Column('brightdata_token_updated_at', sa.DateTime(timezone=True), nullable=True))
    # Per-provider filter config for brightdata feeds (sub_source/country/experience_level/
    # time_range/domain/date_posted/limit) — one JSONB instead of many columns.
    op.add_column('user_feeds', sa.Column('provider_config', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('user_feeds', 'provider_config')
    op.drop_column('user_credentials', 'brightdata_token_updated_at')
    op.drop_column('user_credentials', 'brightdata_token_enc')
    # NB: Postgres can't DROP an enum value; 'brightdata' stays on jobsource (harmless).

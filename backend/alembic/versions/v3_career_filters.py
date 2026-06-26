"""v3 Career filters — per-filter career analyses (source/feed/domain/market)

Revision ID: v3_career_filters
Revises: v3_governance
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'v3_career_filters'
down_revision = 'v3_governance'
branch_labels = None
depends_on = None


def upgrade():
    # career_analysis: drop the one-per-user unique, add filter columns, add (user_id, filter_hash) unique
    op.add_column('career_analysis', sa.Column('filter_hash', sa.String(100), nullable=False, server_default='all'))
    op.add_column('career_analysis', sa.Column('filter_source', sa.String(50), nullable=True))
    op.add_column('career_analysis', sa.Column('filter_feed_id', UUID(as_uuid=True), nullable=True))
    op.add_column('career_analysis', sa.Column('filter_domain_cv_id', UUID(as_uuid=True), nullable=True))
    op.add_column('career_analysis', sa.Column('filter_market', sa.String(20), nullable=True))
    op.add_column('career_analysis', sa.Column('filter_label', sa.String(100), nullable=False, server_default='All jobs'))
    # Drop the auto-named unique constraint on user_id (Postgres: <table>_<col>_key)
    op.drop_constraint('career_analysis_user_id_key', 'career_analysis', type_='unique')
    op.create_index('ix_career_analysis_user_filter', 'career_analysis', ['user_id', 'filter_hash'], unique=True)

    op.add_column('career_roadmap_items', sa.Column('filter_hash', sa.String(100), nullable=False, server_default='all'))


def downgrade():
    op.drop_column('career_roadmap_items', 'filter_hash')
    op.drop_index('ix_career_analysis_user_filter', table_name='career_analysis')
    op.create_unique_constraint('career_analysis_user_id_key', 'career_analysis', ['user_id'])
    for c in ['filter_label', 'filter_market', 'filter_domain_cv_id', 'filter_feed_id', 'filter_source', 'filter_hash']:
        op.drop_column('career_analysis', c)

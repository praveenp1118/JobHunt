"""v3 Community Insights — anonymised job-search insight sharing

Revision ID: v3_community
Revises: v3_job_s1_tokens
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'v3_community'
down_revision = 'v3_job_s1_tokens'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'community_job_insights',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company', sa.String(255), nullable=False),
        sa.Column('role_normalized', sa.String(255), nullable=False),
        sa.Column('market', sa.String(10), nullable=True),
        sa.Column('jd_hash', sa.String(64), nullable=True),
        sa.Column('contributor_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_s1', sa.Float(), nullable=True),
        sa.Column('avg_s1d', sa.Float(), nullable=True),
        sa.Column('best_domain_cv_label', sa.String(255), nullable=True),
        sa.Column('jd_highlights', JSONB, nullable=True),
        sa.Column('keyword_patterns', JSONB, nullable=True),
        sa.Column('tailoring_patterns', JSONB, nullable=True),
        sa.Column('response_data', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_community_company_role', 'community_job_insights', ['company', 'role_normalized'])
    op.create_index('ix_community_jd_hash', 'community_job_insights', ['jd_hash'])
    op.create_index('ix_community_contributor_count', 'community_job_insights', ['contributor_count'])

    op.create_table(
        'community_contributions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('insight_id', UUID(as_uuid=True),
                  sa.ForeignKey('community_job_insights.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contributed_scores', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('contributed_highlights', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('contributed_tailoring', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_anonymous', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_community_contrib_user', 'community_contributions', ['user_id'])

    op.add_column('user_preferences', sa.Column(
        'community_sharing_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('user_preferences', 'community_sharing_enabled')
    op.drop_table('community_contributions')
    op.drop_table('community_job_insights')

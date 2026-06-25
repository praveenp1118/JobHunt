"""v3 Career Insights — gap analysis, roadmap, questions, community

Revision ID: v3_career_insights
Revises: v3_community
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'v3_career_insights'
down_revision = 'v3_community'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'career_analysis',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  unique=True, nullable=False),
        sa.Column('readiness_score', sa.Float(), nullable=True),
        sa.Column('keywords_score', sa.Float(), nullable=True),
        sa.Column('skills_score', sa.Float(), nullable=True),
        sa.Column('experience_score', sa.Float(), nullable=True),
        sa.Column('certifications_score', sa.Float(), nullable=True),
        sa.Column('analysis_json', JSONB, nullable=True),
        sa.Column('jd_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_analysed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'career_roadmap_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('impact_pct', sa.Float(), nullable=True),
        sa.Column('timeframe', sa.String(20), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_career_roadmap_user', 'career_roadmap_items', ['user_id'])

    op.create_table(
        'career_questions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_key', sa.String(50), nullable=False),
        sa.Column('answer', sa.String(500), nullable=True),
        sa.Column('answered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_career_q_user_key', 'career_questions', ['user_id', 'question_key'], unique=True)

    op.create_table(
        'community_career_insights',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('role_category', sa.String(100), nullable=False),
        sa.Column('insight_type', sa.String(30), nullable=False),
        sa.Column('insight_value', sa.String(255), nullable=False),
        sa.Column('frequency_pct', sa.Float(), nullable=True),
        sa.Column('contributor_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_stories', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_community_career_role', 'community_career_insights', ['role_category'])


def downgrade():
    op.drop_table('community_career_insights')
    op.drop_table('career_questions')
    op.drop_table('career_roadmap_items')
    op.drop_table('career_analysis')

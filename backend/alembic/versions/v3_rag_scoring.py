"""v3 Hybrid-RAG scoring — CV essence + per-user scoring config

Revision ID: v3_rag_scoring
Revises: v3_career_filters
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'v3_rag_scoring'
down_revision = 'v3_career_filters'
branch_labels = None
depends_on = None


def upgrade():
    # CV essence
    op.add_column('master_cvs', sa.Column('essence_json', JSONB, nullable=True))
    op.add_column('master_cvs', sa.Column('essence_computed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('master_cvs', sa.Column('essence_version', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('domain_cvs', sa.Column('essence_json', JSONB, nullable=True))
    op.add_column('domain_cvs', sa.Column('essence_computed_at', sa.DateTime(timezone=True), nullable=True))

    # Scoring config on user_preferences
    cols = [
        ('scoring_preset', sa.String(20), 'balanced'),
        ('keyword_match_threshold', sa.Integer(), '3'),
        ('s1_essence_model', sa.String(50), 'claude-haiku-4-5'),
        ('s1_essence_reject_below', sa.Integer(), '50'),
        ('s1_full_model', sa.String(50), 'claude-sonnet-4-6'),
        ('s1_borderline_low', sa.Integer(), '50'),
        ('s1_borderline_high', sa.Integer(), '74'),
        ('domain_score_model', sa.String(50), 'claude-haiku-4-5'),
        ('domain_score_min_s1', sa.Integer(), '55'),
        ('career_model', sa.String(50), 'claude-sonnet-4-6'),
        ('scoring_batch_size', sa.Integer(), '12'),
    ]
    for name, typ, default in cols:
        op.add_column('user_preferences', sa.Column(name, typ, nullable=False, server_default=default))


def downgrade():
    for name in ['scoring_batch_size', 'career_model', 'domain_score_min_s1', 'domain_score_model',
                 's1_borderline_high', 's1_borderline_low', 's1_full_model', 's1_essence_reject_below',
                 's1_essence_model', 'keyword_match_threshold', 'scoring_preset']:
        op.drop_column('user_preferences', name)
    op.drop_column('domain_cvs', 'essence_computed_at')
    op.drop_column('domain_cvs', 'essence_json')
    op.drop_column('master_cvs', 'essence_version')
    op.drop_column('master_cvs', 'essence_computed_at')
    op.drop_column('master_cvs', 'essence_json')

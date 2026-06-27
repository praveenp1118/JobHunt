"""v3 ATS + Pursuit dual scoring — 6 score fields per job + display prefs

Revision ID: v3_ats_pursuit
Revises: v3_email_source
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'v3_ats_pursuit'
down_revision = 'v3_email_source'
branch_labels = None
depends_on = None


def upgrade():
    for col in ('ats_master', 'pursuit_master', 'ats_domain', 'pursuit_domain',
                'ats_tailored', 'pursuit_tailored'):
        op.add_column('jobs', sa.Column(col, sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('score_components', JSONB(), nullable=True))
    op.create_index('ix_jobs_ats_master', 'jobs', ['ats_master'])
    op.create_index('ix_jobs_pursuit_master', 'jobs', ['pursuit_master'])
    op.add_column('user_preferences', sa.Column(
        'default_score_view', sa.String(20), nullable=False, server_default='pursuit'))
    op.add_column('user_preferences', sa.Column(
        'score_pill_style', sa.String(20), nullable=False, server_default='dual_ring'))


def downgrade():
    op.drop_column('user_preferences', 'score_pill_style')
    op.drop_column('user_preferences', 'default_score_view')
    op.drop_index('ix_jobs_pursuit_master', table_name='jobs')
    op.drop_index('ix_jobs_ats_master', table_name='jobs')
    for col in ('score_components', 'pursuit_tailored', 'ats_tailored', 'pursuit_domain',
                'ats_domain', 'pursuit_master', 'ats_master'):
        op.drop_column('jobs', col)

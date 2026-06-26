"""v3 Night-batch scoring — pending job status + per-user scoring timing

Revision ID: v3_night_batch
Revises: v3_rag_scoring
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_night_batch'
down_revision = 'v3_rag_scoring'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE runtype ADD VALUE IF NOT EXISTS 'night_batch'")
    op.add_column('jobs', sa.Column('scoring_status', sa.String(20), nullable=False, server_default='scored'))
    op.create_index('ix_jobs_user_scoring_status', 'jobs', ['user_id', 'scoring_status'])
    op.add_column('user_preferences', sa.Column('scoring_timing', sa.String(20), nullable=False, server_default='immediate'))
    op.add_column('user_preferences', sa.Column('night_batch_time', sa.String(10), nullable=False, server_default='02:00'))


def downgrade():
    op.drop_column('user_preferences', 'night_batch_time')
    op.drop_column('user_preferences', 'scoring_timing')
    op.drop_index('ix_jobs_user_scoring_status', table_name='jobs')
    op.drop_column('jobs', 'scoring_status')

"""v3 per-job S1 scoring cost — jobs.s1_tokens + s1_cost_inr

Only populated for individually-parsed jobs (manual/url) where per-job token
attribution is accurate. Batch-scanned jobs stay NULL (no per-job attribution).

Revision ID: v3_job_s1_tokens
Revises: v3_api_usage_log
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_job_s1_tokens'
down_revision = 'v3_api_usage_log'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('s1_tokens', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('s1_cost_inr', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('jobs', 's1_cost_inr')
    op.drop_column('jobs', 's1_tokens')

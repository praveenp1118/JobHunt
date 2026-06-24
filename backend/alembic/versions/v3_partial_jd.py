"""v3 partial-JD flag — jobs.has_partial_jd

True for jobs whose JD is only a snippet extracted from a job-alert email
(LinkedIn/gated cards), where the full description lives behind portal_url.

Revision ID: v3_partial_jd
Revises: v3_domain_cv_scores
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_partial_jd'
down_revision = 'v3_domain_cv_scores'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column(
        'has_partial_jd', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('jobs', 'has_partial_jd')

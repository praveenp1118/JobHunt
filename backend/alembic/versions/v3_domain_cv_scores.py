"""v3 multi-domain-CV scoring — jobs.s1d + domain_cv_scores + best_domain_cv_id

Each ingested job is scored against the master CV (s1) AND every active domain CV.
domain_cv_scores holds {domain_cv_id: score}; best_domain_cv_id is the top match;
s1d is that best domain CV's score (promoted from breakdown-JSON to a real column).

Revision ID: v3_domain_cv_scores
Revises: v3_activity_log
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'v3_domain_cv_scores'
down_revision = 'v3_activity_log'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('s1d', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('domain_cv_scores', JSONB(), nullable=True))
    op.add_column('jobs', sa.Column(
        'best_domain_cv_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_jobs_best_domain_cv_id', 'jobs', 'domain_cvs',
        ['best_domain_cv_id'], ['id'])
    op.create_index('ix_jobs_best_domain_cv_id', 'jobs', ['best_domain_cv_id'])


def downgrade():
    op.drop_index('ix_jobs_best_domain_cv_id', 'jobs')
    op.drop_constraint('fk_jobs_best_domain_cv_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'best_domain_cv_id')
    op.drop_column('jobs', 'domain_cv_scores')
    op.drop_column('jobs', 's1d')

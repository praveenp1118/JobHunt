"""v2_feed_system_redesign

Revision ID: v2_feed_system
Revises: a1b2c3d4e5f6
Create Date: 2026-06-23

NOTE: This migration was originally authored with down_revision=None, which made
it a second (orphan) root and created a multiple-heads situation — it was never
applied to any database. Re-parented onto a1b2c3d4e5f6 (the live head) to
linearize history into a single head. All operations are additive (nullable
columns + FKs + indexes), so re-parenting is data-safe.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'v2_feed_system'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add V2 columns to user_feeds
    op.add_column('user_feeds', sa.Column('domain_cv_id', UUID(as_uuid=True),
        sa.ForeignKey('domain_cvs.id', ondelete='SET NULL'), nullable=True))
    op.add_column('user_feeds', sa.Column('search_keywords', sa.Text(), nullable=True))
    op.add_column('user_feeds', sa.Column('job_boards', sa.Text(), nullable=True))
    op.add_column('user_feeds', sa.Column('is_auto_generated', sa.Boolean(), nullable=False, server_default='false'))

    op.create_index('ix_user_feeds_domain_cv_id', 'user_feeds', ['domain_cv_id'])

    # Add V2 columns to jobs
    op.add_column('jobs', sa.Column('detected_domain_cv_id', UUID(as_uuid=True),
        sa.ForeignKey('domain_cvs.id'), nullable=True))
    op.add_column('jobs', sa.Column('source_feed_id', UUID(as_uuid=True),
        sa.ForeignKey('user_feeds.id', ondelete='SET NULL'), nullable=True))

    op.create_index('ix_jobs_detected_domain_cv_id', 'jobs', ['detected_domain_cv_id'])

    # Add preferred_model to user_preferences
    op.add_column('user_preferences', sa.Column('preferred_model', sa.String(100), nullable=True))


def downgrade():
    op.drop_index('ix_jobs_detected_domain_cv_id', 'jobs')
    op.drop_column('jobs', 'source_feed_id')
    op.drop_column('jobs', 'detected_domain_cv_id')

    op.drop_index('ix_user_feeds_domain_cv_id', 'user_feeds')
    op.drop_column('user_feeds', 'is_auto_generated')
    op.drop_column('user_feeds', 'job_boards')
    op.drop_column('user_feeds', 'search_keywords')
    op.drop_column('user_feeds', 'domain_cv_id')

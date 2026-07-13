"""dedup_key column for cross-source dedup (Phase 1: add column + non-unique index)

Revision ID: v6_dedup_key_column
Revises: v5_razorpay_columns
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'v6_dedup_key_column'
down_revision = 'v5_razorpay_columns'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable + NON-unique for now. scripts/dedup_resolve.py --apply backfills it and
    # removes existing duplicates; the UNIQUE index lands in v7 afterwards.
    op.add_column('jobs', sa.Column('dedup_key', sa.String(length=512), nullable=True))
    op.create_index('ix_jobs_dedup_key', 'jobs', ['dedup_key'])


def downgrade():
    op.drop_index('ix_jobs_dedup_key', table_name='jobs')
    op.drop_column('jobs', 'dedup_key')

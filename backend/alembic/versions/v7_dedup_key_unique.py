"""UNIQUE (user_id, dedup_key) — Phase 1 final step, after the backfill de-dupes

Revision ID: v7_dedup_key_unique
Revises: v6_dedup_key_column
Create Date: 2026-07-13

Run scripts/dedup_resolve.py --apply BEFORE this migration (it backfills dedup_key and
removes duplicate rows). The guard below refuses to create the index if any duplicate
(user_id, dedup_key) group remains, so a skipped/failed backfill can't build a broken index.
"""
from alembic import op
import sqlalchemy as sa

revision = 'v7_dedup_key_unique'
down_revision = 'v6_dedup_key_column'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # NULL dedup_key rows are ignored (Postgres treats NULLs as distinct); only real
    # (user_id, dedup_key) collisions block the unique index.
    remaining = conn.execute(sa.text(
        "SELECT count(*) FROM ("
        "  SELECT user_id, dedup_key FROM jobs WHERE dedup_key IS NOT NULL "
        "  GROUP BY user_id, dedup_key HAVING count(*) > 1"
        ") d")).scalar()
    if remaining:
        raise RuntimeError(
            f"{remaining} (user_id, dedup_key) duplicate group(s) remain — run "
            "`python -m app.scripts.dedup_resolve --apply` before this migration.")
    op.create_index('uq_jobs_user_dedup', 'jobs', ['user_id', 'dedup_key'], unique=True)


def downgrade():
    op.drop_index('uq_jobs_user_dedup', table_name='jobs')

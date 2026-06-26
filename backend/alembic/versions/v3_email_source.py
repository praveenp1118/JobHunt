"""v3 Email-to-JobHunt source — distinct from manual

Revision ID: v3_email_source
Revises: v3_optimization
Create Date: 2026-06-27
"""
from alembic import op

revision = 'v3_email_source'
down_revision = 'v3_optimization'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE jobsource ADD VALUE IF NOT EXISTS 'email_to_jobhunt'")


def downgrade():
    # Postgres enum values cannot be dropped without recreating the type — no-op.
    pass

"""v3 Optimization — cached JD highlights per job

Revision ID: v3_optimization
Revises: v3_email_to_jobhunt
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'v3_optimization'
down_revision = 'v3_email_to_jobhunt'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('jd_highlights_json', JSONB(), nullable=True))


def downgrade():
    op.drop_column('jobs', 'jd_highlights_json')

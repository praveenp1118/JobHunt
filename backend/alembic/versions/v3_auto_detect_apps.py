"""v3 Auto-detect external applications — toggle pref

Revision ID: v3_auto_detect_apps
Revises: v3_night_batch
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_auto_detect_apps'
down_revision = 'v3_night_batch'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_preferences', sa.Column(
        'auto_detect_applications', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    op.drop_column('user_preferences', 'auto_detect_applications')

"""v3 Email to JobHunt — save-job email pref + classification enum value

Revision ID: v3_email_to_jobhunt
Revises: v3_auto_detect_apps
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_email_to_jobhunt'
down_revision = 'v3_auto_detect_apps'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE emailclassification ADD VALUE IF NOT EXISTS 'save_job'")
    op.add_column('user_preferences', sa.Column(
        'enable_email_to_jobhunt', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    op.drop_column('user_preferences', 'enable_email_to_jobhunt')

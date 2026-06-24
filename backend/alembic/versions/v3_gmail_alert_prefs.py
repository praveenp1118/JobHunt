"""v3 gmail job alert parser — UserPreferences settings

Revision ID: v3_gmail_alert_prefs
Revises: v3_gmail_job_alerts
Create Date: 2026-06-23

Adds the 3 user-facing controls for the Gmail job-alert parser:
  - parse_job_alerts (bool, default True)
  - job_alert_max_links (int, default 10)
  - job_alert_title_filter (bool, default True)
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_gmail_alert_prefs'
down_revision = 'v3_gmail_job_alerts'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_preferences', sa.Column('parse_job_alerts', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('user_preferences', sa.Column('job_alert_max_links', sa.Integer(), nullable=False, server_default='10'))
    op.add_column('user_preferences', sa.Column('job_alert_title_filter', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    op.drop_column('user_preferences', 'job_alert_title_filter')
    op.drop_column('user_preferences', 'job_alert_max_links')
    op.drop_column('user_preferences', 'parse_job_alerts')

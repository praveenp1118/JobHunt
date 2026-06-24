"""v3 activity dashboard — run_logs.details -> JSONB + email_alert_logs table

Revision ID: v3_activity_log
Revises: v3_gmail_alert_prefs
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'v3_activity_log'
down_revision = 'v3_gmail_alert_prefs'
branch_labels = None
depends_on = None


def upgrade():
    # run_logs.details Text -> JSONB (currently all NULL, so the cast is safe)
    op.alter_column(
        'run_logs', 'details',
        existing_type=sa.Text(),
        type_=JSONB(),
        postgresql_using='details::jsonb',
        existing_nullable=True,
    )

    op.create_table(
        'email_alert_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('poll_run_id', UUID(as_uuid=True),
                  sa.ForeignKey('run_logs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email_subject', sa.Text(), nullable=True),
        sa.Column('sender', sa.String(length=255), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('links_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('links_gated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('links_public', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('links_below_threshold', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('links_duplicate', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('jobs_saved', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('saved_job_ids', JSONB(), nullable=True),
        sa.Column('skip_reasons', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_email_alert_logs_user_id', 'email_alert_logs', ['user_id'])
    op.create_index('ix_email_alert_logs_received_at', 'email_alert_logs', ['received_at'])


def downgrade():
    op.drop_index('ix_email_alert_logs_received_at', 'email_alert_logs')
    op.drop_index('ix_email_alert_logs_user_id', 'email_alert_logs')
    op.drop_table('email_alert_logs')
    op.alter_column(
        'run_logs', 'details',
        existing_type=JSONB(),
        type_=sa.Text(),
        postgresql_using='details::text',
        existing_nullable=True,
    )

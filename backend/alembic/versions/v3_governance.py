"""v3 Governance — deletion/marketing fields, key-rotation timestamps, rate_limit_log, audit_logs

Revision ID: v3_governance
Revises: v3_gdpr_consent
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'v3_governance'
down_revision = 'v3_gdpr_consent'
branch_labels = None
depends_on = None


def upgrade():
    # User governance fields (gdpr_consent_at already added in v3_gdpr_consent)
    op.add_column('users', sa.Column('marketing_consent', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('data_deletion_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('data_deletion_scheduled_at', sa.DateTime(timezone=True), nullable=True))

    # Credential key-rotation timestamps
    op.add_column('user_credentials', sa.Column('anthropic_key_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_credentials', sa.Column('apify_token_updated_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'rate_limit_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_rate_limit_user_action_window', 'rate_limit_log', ['user_id', 'action', 'window_start'])

    op.create_table(
        'audit_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('details', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_user_created', 'audit_logs', ['user_id', 'created_at'])
    op.create_index('ix_audit_action_created', 'audit_logs', ['action', 'created_at'])


def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('rate_limit_log')
    op.drop_column('user_credentials', 'apify_token_updated_at')
    op.drop_column('user_credentials', 'anthropic_key_updated_at')
    op.drop_column('users', 'data_deletion_scheduled_at')
    op.drop_column('users', 'data_deletion_requested_at')
    op.drop_column('users', 'marketing_consent')

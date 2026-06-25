"""v3 API usage log — api_usage_logs (Anthropic + Apify call tracking)

Revision ID: v3_api_usage_log
Revises: v3_chat
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'v3_api_usage_log'
down_revision = 'v3_chat'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_usage_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=True),
        sa.Column('entity_id', sa.String(100), nullable=True),
        sa.Column('entity_label', sa.String(255), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
        sa.Column('estimated_cost_inr', sa.Float(), nullable=True),
        sa.Column('actor_id', sa.String(200), nullable=True),
        sa.Column('runs_requested', sa.Integer(), nullable=True),
        sa.Column('runs_returned', sa.Integer(), nullable=True),
        sa.Column('jobs_saved', sa.Integer(), nullable=True),
        sa.Column('result_summary', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_api_usage_user_created', 'api_usage_logs', ['user_id', 'created_at'])
    op.create_index('ix_api_usage_user_provider', 'api_usage_logs', ['user_id', 'provider'])
    op.create_index('ix_api_usage_user_category', 'api_usage_logs', ['user_id', 'category'])


def downgrade():
    op.drop_table('api_usage_logs')

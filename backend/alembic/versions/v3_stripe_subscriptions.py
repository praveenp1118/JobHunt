"""v3 Stripe subscriptions — users.stripe_customer_id + subscription_* fields

Adds JobHunt Pro subscription state to the users table:
  stripe_customer_id, subscription_status (inactive/active/expired/cancelled/past_due),
  subscription_plan (none/pro), subscription_end, subscription_id.

Revision ID: v3_stripe_subscriptions
Revises: v3_partial_jd
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_stripe_subscriptions'
down_revision = 'v3_partial_jd'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('subscription_status', sa.String(length=20),
                                     nullable=False, server_default='inactive'))
    op.add_column('users', sa.Column('subscription_plan', sa.String(length=20),
                                     nullable=False, server_default='none'))
    op.add_column('users', sa.Column('subscription_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('subscription_id', sa.String(length=100), nullable=True))
    op.create_index('ix_users_stripe_customer_id', 'users', ['stripe_customer_id'])


def downgrade():
    op.drop_index('ix_users_stripe_customer_id', table_name='users')
    op.drop_column('users', 'subscription_id')
    op.drop_column('users', 'subscription_end')
    op.drop_column('users', 'subscription_plan')
    op.drop_column('users', 'subscription_status')
    op.drop_column('users', 'stripe_customer_id')

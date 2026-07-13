"""razorpay subscription columns (parallel to stripe, test mode)

Revision ID: v5_razorpay_columns
Revises: v4_tailor_draft_persistence
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'v5_razorpay_columns'
down_revision = 'v4_tailor_draft_persistence'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('razorpay_customer_id', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('razorpay_subscription_id', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('payment_provider', sa.String(length=20), nullable=True))
    op.create_index('ix_users_razorpay_customer_id', 'users', ['razorpay_customer_id'])
    op.create_index('ix_users_razorpay_subscription_id', 'users', ['razorpay_subscription_id'])


def downgrade():
    op.drop_index('ix_users_razorpay_subscription_id', table_name='users')
    op.drop_index('ix_users_razorpay_customer_id', table_name='users')
    op.drop_column('users', 'payment_provider')
    op.drop_column('users', 'razorpay_subscription_id')
    op.drop_column('users', 'razorpay_customer_id')

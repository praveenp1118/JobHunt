"""add user_feeds.actor_name (Apify actor display name for scanner input matching)

Revision ID: b2c3d4e5f6a7
Revises: v2_feed_system
Create Date: 2026-06-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'v2_feed_system'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_feeds', sa.Column('actor_name', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('user_feeds', 'actor_name')

"""add user profile fields (linkedin_url, phone, current_location, salary_expectation)

Revision ID: a1b2c3d4e5f6
Revises: f6a226b07b5f
Create Date: 2026-06-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f6a226b07b5f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('linkedin_url', sa.String(length=512), nullable=True))
    op.add_column('users', sa.Column('phone', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('current_location', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('salary_expectation', sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column('users', 'salary_expectation')
    op.drop_column('users', 'current_location')
    op.drop_column('users', 'phone')
    op.drop_column('users', 'linkedin_url')

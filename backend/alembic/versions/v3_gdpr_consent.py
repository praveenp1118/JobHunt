"""v3 GDPR consent timestamp on users

Revision ID: v3_gdpr_consent
Revises: v3_cv_template
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_gdpr_consent'
down_revision = 'v3_cv_template'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('gdpr_consent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('users', 'gdpr_consent_at')

"""v3 Dual-score scan gate — auto_dual_score_on_scan preference

Revision ID: v3_dual_scan_gate
Revises: v3_ats_pursuit
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'v3_dual_scan_gate'
down_revision = 'v3_ats_pursuit'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_preferences', sa.Column(
        'auto_dual_score_on_scan', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('user_preferences', 'auto_dual_score_on_scan')

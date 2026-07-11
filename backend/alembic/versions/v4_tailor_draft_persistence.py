"""v4 Tailor draft persistence

Additive, nullable-only columns on tailored_cvs so a tailored draft can be restored
on return (and Claude only re-runs on an explicit "Re-tailor"):
  - status (String(20), default 'generated')  : 'generated' | 'applied'
  - applied_at (DateTime tz, nullable)
  - base_domain_cv_version (Integer, nullable) : domain CV version at tailor time (staleness)
  - jd_hash (String(64), nullable)             : JD hash at tailor time (staleness)

Backfill: existing rows with a non-empty cv_md were already applied -> status='applied';
everything else keeps the 'generated' default. Snapshots stay NULL for existing rows
(treated as "not stale" — flag only, never auto-re-run).

Revision ID: v4_tailor_draft_persistence
Revises: v3_invite_or_pay
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'v4_tailor_draft_persistence'
down_revision = 'v3_invite_or_pay'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tailored_cvs', sa.Column(
        'status', sa.String(length=20), nullable=False, server_default='generated'))
    op.add_column('tailored_cvs', sa.Column(
        'applied_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tailored_cvs', sa.Column(
        'base_domain_cv_version', sa.Integer(), nullable=True))
    op.add_column('tailored_cvs', sa.Column(
        'jd_hash', sa.String(length=64), nullable=True))

    # Backfill: rows already applied (cv_md filled) -> 'applied'; the rest stay 'generated'.
    op.execute("UPDATE tailored_cvs SET status='applied' WHERE cv_md IS NOT NULL AND cv_md <> ''")


def downgrade():
    op.drop_column('tailored_cvs', 'jd_hash')
    op.drop_column('tailored_cvs', 'base_domain_cv_version')
    op.drop_column('tailored_cvs', 'applied_at')
    op.drop_column('tailored_cvs', 'status')

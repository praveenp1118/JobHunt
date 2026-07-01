"""v3 Invite-or-pay registration gate

Adds the invite-or-pay access model:
  - invitation_keys   : single-use redeemable keys (grants N free days)
  - extension_requests: in-app queue for invited users to request more free time
  - users.entitlement_source : 'invite' | 'stripe' | NULL (records how the current
    entitlement was obtained; REUSES the existing subscription_status/subscription_end)

Revision ID: v3_invite_or_pay
Revises: v3_dual_scan_gate
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'v3_invite_or_pay'
down_revision = 'v3_dual_scan_gate'
branch_labels = None
depends_on = None


def upgrade():
    # ── users.entitlement_source ──────────────────────────────────────────────
    op.add_column('users', sa.Column('entitlement_source', sa.String(length=20), nullable=True))

    # ── invitation_keys ───────────────────────────────────────────────────────
    op.create_table(
        'invitation_keys',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), nullable=False),
        sa.Column('grants_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('key_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('redeemed_by', UUID(as_uuid=True), nullable=True),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['redeemed_by'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_invitation_keys_code'), 'invitation_keys', ['code'], unique=True)
    op.create_index(op.f('ix_invitation_keys_created_by'), 'invitation_keys', ['created_by'])
    op.create_index(op.f('ix_invitation_keys_redeemed_by'), 'invitation_keys', ['redeemed_by'])

    # ── extension_requests ────────────────────────────────────────────────────
    op.create_table(
        'extension_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_extension_requests_user_id'), 'extension_requests', ['user_id'])


def downgrade():
    op.drop_index(op.f('ix_extension_requests_user_id'), table_name='extension_requests')
    op.drop_table('extension_requests')
    op.drop_index(op.f('ix_invitation_keys_redeemed_by'), table_name='invitation_keys')
    op.drop_index(op.f('ix_invitation_keys_created_by'), table_name='invitation_keys')
    op.drop_index(op.f('ix_invitation_keys_code'), table_name='invitation_keys')
    op.drop_table('invitation_keys')
    op.drop_column('users', 'entitlement_source')

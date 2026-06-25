"""v3 CV Template — aesthetic + content rules, per-domain overrides

Revision ID: v3_cv_template
Revises: v3_career_insights
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'v3_cv_template'
down_revision = 'v3_career_insights'
branch_labels = None
depends_on = None

_NEVER_MODIFY = sa.text("""'["EDUCATION", "CERTIFICATIONS"]'::jsonb""")
_SECTION_ORDER = sa.text("""'["SUMMARY", "EXPERIENCE", "EDUCATION", "CERTIFICATIONS"]'::jsonb""")


def upgrade():
    op.create_table(
        'cv_template',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  unique=True, nullable=False),
        sa.Column('font_family', sa.String(50), nullable=False, server_default='Calibri'),
        sa.Column('font_size', sa.Integer(), nullable=False, server_default='11'),
        sa.Column('heading_font_family', sa.String(50), nullable=False, server_default='Calibri'),
        sa.Column('heading_font_size', sa.Integer(), nullable=False, server_default='14'),
        sa.Column('heading_bold', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('margin_size', sa.String(20), nullable=False, server_default='normal'),
        sa.Column('line_spacing', sa.Float(), nullable=False, server_default='1.15'),
        sa.Column('bullet_style', sa.String(10), nullable=False, server_default='•'),
        sa.Column('accent_color', sa.String(7), nullable=False, server_default='#1a1a1a'),
        sa.Column('max_pages', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('overflow_action', sa.String(20), nullable=False, server_default='warn'),
        sa.Column('never_modify_sections', JSONB, nullable=False, server_default=_NEVER_MODIFY),
        sa.Column('section_order', JSONB, nullable=False, server_default=_SECTION_ORDER),
        sa.Column('max_words', sa.Integer(), nullable=False, server_default='600'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'domain_cv_template_overrides',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('domain_cv_id', UUID(as_uuid=True), sa.ForeignKey('domain_cvs.id', ondelete='CASCADE'),
                  unique=True, nullable=False),
        sa.Column('font_family', sa.String(50), nullable=True),
        sa.Column('font_size', sa.Integer(), nullable=True),
        sa.Column('max_pages', sa.Integer(), nullable=True),
        sa.Column('overflow_action', sa.String(20), nullable=True),
        sa.Column('never_modify_sections', JSONB, nullable=True),
        sa.Column('section_order', JSONB, nullable=True),
        sa.Column('max_words', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_domain_cv_template_user', 'domain_cv_template_overrides', ['user_id'])


def downgrade():
    op.drop_table('domain_cv_template_overrides')
    op.drop_table('cv_template')

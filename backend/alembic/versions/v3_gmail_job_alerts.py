"""v3 gmail job alert parser — email classification + thread/job columns

Revision ID: v3_gmail_job_alerts
Revises: b2c3d4e5f6a7
Create Date: 2026-06-23

Adds:
  - emailclassification enum value 'job_alert'
  - jobsource enum value 'gmail_alert'
  - email_threads: is_job_alert, jobs_extracted, jobs_saved
  - email_threads.job_id -> nullable (alert digests aren't tied to one job)
  - jobs.source_email_id (FK -> email_threads.id, the alert it came from)

NOTE: UserPreferences fields (parse_job_alerts, job_alert_max_links,
job_alert_title_filter) are added in a SEPARATE migration (build order step 5).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'v3_gmail_job_alerts'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # New enum values must be committed before they can be used; a value cannot
    # be ADDed and used in the same transaction, so run these in autocommit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE emailclassification ADD VALUE IF NOT EXISTS 'job_alert'")
        op.execute("ALTER TYPE jobsource ADD VALUE IF NOT EXISTS 'gmail_alert'")

    # EmailThread: job-alert metadata
    op.add_column('email_threads', sa.Column('is_job_alert', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('email_threads', sa.Column('jobs_extracted', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('email_threads', sa.Column('jobs_saved', sa.Integer(), nullable=False, server_default='0'))

    # Job-alert digest emails aren't tied to a single job -> allow null job_id
    op.alter_column('email_threads', 'job_id', existing_type=UUID(as_uuid=True), nullable=True)

    # Job: link back to the alert email it was extracted from
    op.add_column('jobs', sa.Column(
        'source_email_id', UUID(as_uuid=True),
        sa.ForeignKey('email_threads.id', ondelete='SET NULL'), nullable=True,
    ))


def downgrade():
    op.drop_column('jobs', 'source_email_id')
    op.alter_column('email_threads', 'job_id', existing_type=UUID(as_uuid=True), nullable=False)
    op.drop_column('email_threads', 'jobs_saved')
    op.drop_column('email_threads', 'jobs_extracted')
    op.drop_column('email_threads', 'is_job_alert')
    # Postgres can't DROP an enum value, so 'job_alert' / 'gmail_alert' remain on
    # the enum types after downgrade (harmless).

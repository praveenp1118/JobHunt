from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "jobhunt",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.gmail_tasks",
        "app.tasks.scanner_tasks",
        "app.tasks.governance_tasks",
        "app.tasks.scoring_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# ── Beat schedule ─────────────────────────────────────────────────────────────
# All wall-clock crontab() anchors (beat runs UTC, enable_utc=True) so they fire at
# FIXED times regardless of when beat/deploys restart. (Plain-interval schedules
# reset their countdown on every beat restart, which can starve the weekly scan.)
celery_app.conf.beat_schedule = {
    # Weekly job scan — Sunday 17:30 UTC = 11:00 PM IST
    "weekly-job-scan": {
        "task": "tasks.weekly_job_scan",
        "schedule": crontab(day_of_week="sun", hour=17, minute=30),
    },
    # Hourly Gmail poll — top of every hour (UTC)
    "poll-gmail-hourly": {
        "task": "tasks.poll_gmail_all_users",
        "schedule": crontab(minute=0),
    },
    # Daily ghosting check — 01:00 UTC = 06:30 AM IST
    "check-ghosted-daily": {
        "task": "tasks.check_ghosted_jobs",
        "schedule": crontab(hour=1, minute=0),
    },
    # Daily purge of accounts past their 30-day deletion grace window — 02:00 UTC = 07:30 AM IST
    "purge-deleted-accounts-daily": {
        "task": "tasks.purge_deleted_accounts",
        "schedule": crontab(hour=2, minute=0),
    },
    # Nightly batch scoring of 'pending' jobs — 21:30 UTC = 02:00 AM IST
    "night-batch-scoring": {
        "task": "tasks.score_pending_jobs_batch",
        "schedule": crontab(hour=21, minute=30),
    },
}

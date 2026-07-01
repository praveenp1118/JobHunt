"""
Celery tasks for Gmail polling.
Runs hourly by default (configurable in Settings).
"""
from app.worker import celery_app


@celery_app.task(name="tasks.poll_gmail_all_users", bind=True, max_retries=2)
def poll_gmail_all_users(self):
    """
    Hourly task: poll Gmail for all users who have Gmail configured.
    Runs in background via Celery Beat.
    """
    import asyncio
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_poll_all_users_async())
    finally:
        loop.run_until_complete(engine.dispose())  # avoid cross-loop pool reuse
        loop.close()


async def _poll_all_users_async():
    """Async implementation of the Gmail poll task."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials, UserPreferences
    from app.models.job import Job, EmailThread, JobStatus, EmailDirection, EmailClassification
    from app.models.admin import RunLog, RunType, RunStatus
    from app.utils.encryption import decrypt_if_present
    from app.mcp.gmail_mcp import poll_inbox
    from app.agents.gmail_agents import classify_emails_batch, match_email_to_job
    from app.utils.email import send_notification_email
    from app.config import settings

    print("🔄 Starting Gmail poll for all users...")
    results = []

    async with AsyncSessionLocal() as session:
        # Get all users with Gmail configured
        result = await session.execute(
            select(User, UserCredentials)
            .join(UserCredentials, UserCredentials.user_id == User.id)
            .where(
                User.is_active == True,
                UserCredentials.gmail_address.isnot(None),
                UserCredentials.gmail_app_password_enc.isnot(None),
            )
        )
        user_creds = result.all()

        from app.utils.subscription import is_entitled
        for user, creds in user_creds:
            # Skip un-entitled users — the hourly poll classifies/scores via Claude;
            # an inert account must not spend tokens on the platform's schedule.
            if not is_entitled(user):
                continue
            from app.utils.usage_logger import set_usage_user
            set_usage_user(user.id)  # attribute classify/score calls to this user
            # A RunLog per user-poll — its id is passed down so EmailAlertLog rows
            # can link back to this poll (Activity dashboard).
            started = datetime.now(timezone.utc)
            run_log = RunLog(
                user_id=user.id, run_type=RunType.gmail_poll,
                status=RunStatus.running, started_at=started,
            )
            session.add(run_log)
            await session.flush()  # assign run_log.id

            try:
                gmail_address = creds.gmail_address
                app_password = decrypt_if_present(creds.gmail_app_password_enc)

                # Poll interval from preferences
                prefs_result = await session.execute(
                    select(UserPreferences).where(UserPreferences.user_id == user.id)
                )
                prefs = prefs_result.scalar_one_or_none()
                poll_hours = (prefs.gmail_poll_interval_minutes // 60 + 1) if prefs else 2

                since_dt = datetime.now(timezone.utc) - timedelta(hours=poll_hours)

                # Use the user's own Anthropic key (decrypted), falling back to the
                # platform key — mirrors the manual /poll endpoint. The hourly task
                # previously only used the (unset) platform key → classification failed.
                anthropic_key = (
                    decrypt_if_present(creds.anthropic_api_key_enc)
                    if creds.anthropic_api_key_enc else None
                ) or settings.platform_anthropic_api_key or settings.anthropic_api_key

                # Fetch and process (reusing router logic)
                from app.routers.gmail import _process_inbox_emails
                summary = await _process_inbox_emails(
                    user=user,
                    gmail_address=gmail_address,
                    app_password=app_password,
                    since_dt=since_dt,
                    session=session,
                    anthropic_key=anthropic_key,
                    poll_run_id=run_log.id,
                )

                run_log.status = RunStatus.error if summary.get("errors") else RunStatus.success
                run_log.jobs_found = summary.get("new_emails", 0)
                run_log.jobs_added = summary.get("jobs_from_alerts", 0) + summary.get("jobs_updated", 0)
                run_log.details = {
                    "emails_checked": summary.get("emails_checked", 0),
                    "new_emails": summary.get("new_emails", 0),
                    "alerts_processed": summary.get("alerts_processed", 0),
                    "jobs_from_alerts": summary.get("jobs_from_alerts", 0),
                    "jobs_updated": summary.get("jobs_updated", 0),
                    "hitl_flagged": summary.get("hitl_flagged", 0),
                }
                run_log.completed_at = datetime.now(timezone.utc)
                run_log.duration_seconds = (run_log.completed_at - started).total_seconds()
                results.append({"user": user.email, **summary})
                print(f"✅ Polled {user.email}: {summary}")

            except Exception as e:
                run_log.status = RunStatus.error
                run_log.error_message = str(e)
                run_log.completed_at = datetime.now(timezone.utc)
                print(f"❌ Gmail poll failed for {user.email}: {e}")
                results.append({"user": user.email, "error": str(e)})

            await session.commit()

    print(f"✅ Gmail poll complete: {len(results)} users processed")
    return results


@celery_app.task(name="tasks.check_ghosted_jobs", bind=True)
def check_ghosted_jobs(self):
    """
    Daily task: auto-flag applied jobs as Ghosted after X days of no response.
    """
    import asyncio
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_check_ghosted_async())
    finally:
        loop.run_until_complete(engine.dispose())  # avoid cross-loop pool reuse
        loop.close()


async def _check_ghosted_async():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.job import Job, JobStatus
    from app.models.user import UserPreferences
    from app.models.admin import RunLog, RunType, RunStatus
    from app.config import settings

    print("🔄 Checking for ghosted jobs...")
    ghosted_count = 0

    async with AsyncSessionLocal() as session:
        started = datetime.now(timezone.utc)
        run_log = RunLog(run_type=RunType.ghost_check, status=RunStatus.running, started_at=started)
        session.add(run_log)
        await session.flush()

        result = await session.execute(
            select(Job).where(
                Job.status == JobStatus.applied,
                Job.applied_at.isnot(None),
            )
        )
        applied_jobs = result.scalars().all()

        for job in applied_jobs:
            # Get user's ghost threshold
            prefs_result = await session.execute(
                select(UserPreferences).where(UserPreferences.user_id == job.user_id)
            )
            prefs = prefs_result.scalar_one_or_none()
            ghost_days = prefs.ghost_after_days if prefs else settings.ghost_after_days

            days_since = (datetime.now(timezone.utc) - job.applied_at).days
            if days_since >= ghost_days:
                job.status = JobStatus.ghosted
                job.ghosted_at = datetime.now(timezone.utc)
                ghosted_count += 1

        run_log.status = RunStatus.success
        run_log.jobs_found = len(applied_jobs)   # applied jobs checked
        run_log.jobs_added = ghosted_count        # newly ghosted
        run_log.details = {"checked": len(applied_jobs), "ghosted": ghosted_count}
        run_log.completed_at = datetime.now(timezone.utc)
        run_log.duration_seconds = (run_log.completed_at - started).total_seconds()
        await session.commit()

    print(f"✅ Ghosted {ghosted_count} jobs")
    return {"ghosted": ghosted_count}


@celery_app.task(name="tasks.fetch_partial_jd", bind=True, max_retries=1)
def fetch_partial_jd(self, job_id: str, user_id: str):
    """Background fetch + re-score of a partial-JD job's full description (from portal_url)."""
    import asyncio
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fetch_partial_jd_async(job_id, user_id))
    finally:
        loop.run_until_complete(engine.dispose())  # avoid cross-loop pool reuse
        loop.close()


async def _fetch_partial_jd_async(job_id: str, user_id: str):
    import uuid
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials, UserPreferences
    from app.utils.encryption import decrypt_if_present
    from app.agents.gmail_alert_agent import fetch_and_rescore_partial_job
    from app.config import settings

    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )).scalar_one_or_none()
        if not user:
            return {"status": "user_not_found"}
        creds = (await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id)
        )).scalar_one_or_none()
        anthropic_key = (
            (decrypt_if_present(creds.anthropic_api_key_enc) if creds and creds.anthropic_api_key_enc else None)
            or settings.platform_anthropic_api_key or settings.anthropic_api_key
        )
        prefs = (await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id)
        )).scalar_one_or_none()
        model = (prefs.preferred_model if prefs and getattr(prefs, "preferred_model", None)
                 else settings.anthropic_model)
        from app.utils.usage_logger import set_usage_user
        set_usage_user(user.id)
        result = await fetch_and_rescore_partial_job(uuid.UUID(job_id), user, session, anthropic_key, model)
        print(f"🔁 fetch_partial_jd {job_id}: {result.get('status')}")
        return result


@celery_app.task(name="tasks.score_pasted_jd", bind=True, max_retries=1)
def score_pasted_jd(self, job_id: str, user_id: str):
    """Background S1 + S1d scoring of a partial-JD job from user-pasted JD text
    (already saved to job.jd_raw by POST /jobs/{id}/add-full-jd)."""
    import asyncio
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_score_pasted_jd_async(job_id, user_id))
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


async def _score_pasted_jd_async(job_id: str, user_id: str):
    import uuid
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials, UserPreferences
    from app.utils.encryption import decrypt_if_present
    from app.agents.gmail_alert_agent import rescore_partial_job_from_text
    from app.config import settings

    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )).scalar_one_or_none()
        if not user:
            return {"status": "user_not_found"}
        creds = (await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id)
        )).scalar_one_or_none()
        anthropic_key = (
            (decrypt_if_present(creds.anthropic_api_key_enc) if creds and creds.anthropic_api_key_enc else None)
            or settings.platform_anthropic_api_key or settings.anthropic_api_key
        )
        prefs = (await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id)
        )).scalar_one_or_none()
        model = (prefs.preferred_model if prefs and getattr(prefs, "preferred_model", None)
                 else settings.anthropic_model)
        from app.utils.usage_logger import set_usage_user
        set_usage_user(user.id)
        result = await rescore_partial_job_from_text(uuid.UUID(job_id), user, session, anthropic_key, model)
        print(f"📝 score_pasted_jd {job_id}: {result.get('status')}")
        return result

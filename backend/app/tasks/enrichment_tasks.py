"""Daily opt-in auto-enrich of HIGH-SCORING partial-JD jobs via Bright Data collect-by-URL.

Reuses the SAME path as the "Fetch full JD" button: brightdata_collect_by_url →
rescore_partial_job_from_text (which now also refreshes the ATS/Pursuit dual scores the
Jobs list + Tailor card read). Cost-disciplined: opt-in, high-score only, per-user cap,
per-user BYOK tokens, idempotent (only touches has_partial_jd=true jobs).
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.worker import celery_app

logger = logging.getLogger("jobhunt.enrichment")


@celery_app.task(name="tasks.enrich_high_scoring_partials", bind=True)
def enrich_high_scoring_partials(self):
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_enrich_async())
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


async def _enrich_async():
    from sqlalchemy import select, func, or_
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials, UserPreferences
    from app.models.job import Job
    from app.models.admin import RunLog, RunType, RunStatus
    from app.utils.encryption import decrypt_if_present
    from app.utils.usage_logger import set_usage_user, get_session_usage
    from app.agents.gmail_alert_agent import rescore_partial_job_from_text
    from app.utils.brightdata_client import (brightdata_collect_by_url, detect_sub_source,
                                             BrightDataError)
    from app.config import settings

    if not settings.partial_enrich_enabled:
        return {"skipped": "disabled"}
    cap = settings.partial_enrich_cap

    async with AsyncSessionLocal() as session:
        run_log = RunLog(run_type=RunType.partial_enrich, status=RunStatus.running,
                         started_at=datetime.now(timezone.utc))
        session.add(run_log)
        await session.flush()

        # Opted-in, active users who actually have a Bright Data token.
        rows = (await session.execute(
            select(User, UserCredentials, UserPreferences)
            .join(UserCredentials, UserCredentials.user_id == User.id)
            .join(UserPreferences, UserPreferences.user_id == User.id)
            .where(User.is_active == True,                                       # noqa: E712
                   UserPreferences.auto_enrich_partials == True,                 # noqa: E712
                   UserCredentials.brightdata_token_enc.isnot(None)))).all()

        per_user, total_enriched, total_attempts, errors = [], 0, 0, []
        for user, creds, prefs in rows:
            try:
                bd_token = decrypt_if_present(creds.brightdata_token_enc)
                if not bd_token:                       # defensive (filter already checked)
                    continue
                key = (decrypt_if_present(creds.anthropic_api_key_enc)
                       if creds.anthropic_api_key_enc else None) \
                    or settings.platform_anthropic_api_key or settings.anthropic_api_key
                if not key:
                    per_user.append({"email": user.email, "skipped": "no_anthropic_key"})
                    continue
                threshold = prefs.auto_enrich_threshold or 70
                set_usage_user(user.id)
                cost0 = get_session_usage().get("cost_inr", 0.0)

                # ── THE QUERY: high-scoring, enrichable, capped ──
                score = func.coalesce(Job.s1d, Job.s1)          # best available score
                jobs = (await session.execute(
                    select(Job).where(
                        Job.user_id == user.id,
                        Job.has_partial_jd == True,             # idempotent: only partials  # noqa: E712
                        score >= threshold,                     # HIGH-scoring only (cost gate)
                        or_(Job.portal_url.ilike("%linkedin%"),
                            Job.portal_url.ilike("%indeed%")),  # enrichable via BD collect-by-URL
                    ).order_by(score.desc()).limit(cap))        # best first if capped
                ).scalars().all()

                enriched = failed = 0
                for job in jobs:
                    total_attempts += 1
                    sub = detect_sub_source(job.portal_url)
                    if not sub:                                 # belt-and-braces
                        continue
                    try:
                        rec = await brightdata_collect_by_url(job.portal_url, sub, bd_token)
                    except BrightDataError as e:                # BD failed → leave partial, continue
                        failed += 1
                        logger.warning(f"enrich BD fail {job.id}: {e}")
                        continue
                    jd = ((rec or {}).get("job_description_formatted")
                          or (rec or {}).get("description")
                          or (rec or {}).get("description_text") or "").strip()
                    if len(jd) < 100:                           # gated/thin → leave partial
                        failed += 1
                        continue
                    # Reuse the EXISTING path: save the JD, then rescore (S1/S1d + dual + clears flag).
                    job.jd_raw = jd[:50000]
                    job.jd_md = jd[:50000]
                    await session.flush()
                    try:
                        await rescore_partial_job_from_text(job.id, user, session, key)
                        enriched += 1
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        logger.warning(f"enrich rescore fail {job.id}: {e}")

                user_cost = round(get_session_usage().get("cost_inr", 0.0) - cost0, 2)
                total_enriched += enriched
                per_user.append({                               # cost transparency → run_logs
                    "email": user.email, "candidates": len(jobs), "capped": len(jobs) == cap,
                    "enriched": enriched, "failed": failed,
                    "bd_credits_est": enriched,                 # ~1 Bright Data credit / enriched job
                    "anthropic_cost_inr": user_cost})           # their own Claude spend (dual rescore)
            except Exception as e:  # noqa: BLE001 — never fail the whole run for one user
                errors.append(f"{user.email}: {e}")
                logger.warning(f"enrich user fail {user.email}: {e}")

        run_log.status = RunStatus.success if not errors else RunStatus.partial
        run_log.jobs_added = total_enriched
        run_log.details = {"partial_enrich": True, "cap": cap, "users": len(rows),
                           "total_enriched": total_enriched, "total_attempts": total_attempts,
                           "per_user": per_user}
        run_log.completed_at = datetime.now(timezone.utc)
        run_log.duration_seconds = (run_log.completed_at - run_log.started_at).total_seconds()
        if errors:
            run_log.error_message = "; ".join(errors[:5])
        await session.commit()

    logger.warning(f"partial-enrich: {total_enriched} enriched across {len(rows)} user(s)")
    return {"enriched": total_enriched}

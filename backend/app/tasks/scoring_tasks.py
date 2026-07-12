"""Night-batch scoring — score 'pending' jobs (overnight / manual modes) with the
full 3-stage RAG pipeline. Reused by the nightly Celery task and the 'Score now' endpoint."""
import asyncio
import logging
from datetime import datetime, timezone

from app.worker import celery_app

logger = logging.getLogger("jobhunt.scoring")
NIGHT_BATCH_SIZE = 20


async def score_pending_for_user(user, session, anthropic_key, prefs, job_ids=None) -> dict:
    """Score this user's 'pending' jobs (optionally only `job_ids`). Updates each job's
    s1/s1d/domain_cv_scores/best_domain_cv_id + scoring_status='scored'. Returns stats."""
    from sqlalchemy import select
    from app.models.job import Job
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.domain import IndustryVertical
    from app.agents.rag_scorer import hybrid_rag_score, config_from_prefs
    from app.utils.usage_logger import set_usage_user, get_session_usage

    set_usage_user(user.id)
    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
    master_cv_md = master.content_md if master else ""
    master_essence = master.essence_json if master else None

    q = select(Job).where(Job.user_id == user.id, Job.scoring_status == "pending")
    if job_ids:
        q = q.where(Job.id.in_(job_ids))
    pending = (await session.execute(q)).scalars().all()
    if not pending:
        return {"scored": 0, "cost_inr": 0.0, "tokens": 0, "total": 0}

    config = config_from_prefs(prefs)
    config["scoring_batch_size"] = NIGHT_BATCH_SIZE  # max batch for the cheapest run

    dcv_rows = (await session.execute(
        select(DomainCV.id, DomainCV.content_md, DomainCV.essence_json)
        .where(DomainCV.user_id == user.id, DomainCV.status == CVStatus.active,
               DomainCV.content_md.isnot(None)))).all()
    domain_cvs = [{"id": str(did), "content_md": c, "essence": e} for did, c, e in dcv_rows]

    job_dicts = [{"id": str(j.id), "role": j.role or "", "company": j.company or "",
                  "location": j.location or "", "jd_raw": j.jd_md or j.jd_raw or ""} for j in pending]
    by_id = {str(j.id): j for j in pending}

    cost0 = get_session_usage().get("cost_inr", 0.0)
    rag = await hybrid_rag_score(job_dicts, master_essence, master_cv_md, domain_cvs, config, anthropic_key)

    scored = 0
    import uuid as _uuid
    for rj in rag["jobs"]:
        job = by_id.get(rj.get("_rid") or rj.get("id"))
        if not job:
            continue
        final_s1 = rj.get("s1")
        if final_s1 is None:
            final_s1 = rj.get("_s1_essence")  # stage-2 rejected → keep its essence score
        job.s1 = final_s1
        job.s1d = rj.get("s1d")
        job.domain_cv_scores = rj.get("domain_cv_scores") or None
        bid = rj.get("best_domain_cv_id")
        job.best_domain_cv_id = _uuid.UUID(bid) if bid else None
        job.scoring_status = "scored"
        scored += 1
    await session.commit()

    cost = round(get_session_usage().get("cost_inr", 0.0) - cost0, 2)
    return {"scored": scored, "cost_inr": cost, "tokens": rag["stats"].get("tokens_stage2", 0) + rag["stats"].get("tokens_stage3", 0),
            "total": len(pending), **{k: rag["stats"].get(k, 0) for k in ("stage1_rejected", "stage2_rejected", "stage3_scored")}}


@celery_app.task(name="tasks.backfill_dual_scores", bind=True)
def backfill_dual_scores(self, user_id: str):
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_backfill_async(user_id))
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


async def _backfill_async(user_id: str):
    import uuid as _uuid
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials
    from app.models.cv import MasterCV
    from app.models.job import Job
    from app.models.admin import RunLog, RunType, RunStatus
    from app.agents.dual_scorer import compute_dual_scores
    from app.utils.encryption import decrypt_if_present
    from app.utils.usage_logger import set_usage_user, get_session_usage
    from app.config import settings

    uid = _uuid.UUID(user_id)
    async with AsyncSessionLocal() as session:
        run_log = RunLog(run_type=RunType.night_batch, status=RunStatus.running,
                         started_at=datetime.now(timezone.utc))
        session.add(run_log)
        await session.flush()
        set_usage_user(uid)
        cost0 = get_session_usage().get("cost_inr", 0.0)

        creds = (await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == uid))).scalar_one_or_none()
        key = (decrypt_if_present(creds.anthropic_api_key_enc) if creds and creds.anthropic_api_key_enc else None) \
            or settings.platform_anthropic_api_key or settings.anthropic_api_key
        master = (await session.execute(
            select(MasterCV).where(MasterCV.user_id == uid, MasterCV.is_active == True))).scalars().first()

        # ── MASTER pass (Match column) — jobs with no ats_master yet ──
        scored = 0
        if key and master and master.essence_json:
            jobs = (await session.execute(select(Job).where(
                Job.user_id == uid, Job.jd_raw.isnot(None), Job.ats_master.is_(None)))).scalars().all()
            for job in jobs:
                try:
                    await compute_dual_scores(
                        master.essence_json, master.content_md, job.jd_md or job.jd_raw or "",
                        "master", job=job, anthropic_key=key, session=session)
                    scored += 1
                    await asyncio.sleep(0.2)  # ~5 jobs/sec rate limit
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"backfill score failed for job {job.id}: {e}")

        # ── DOMAIN pass (Best Fit column) — ONLY if the user has an active domain CV ──
        # Mirrors the scanner: S1-score each job's JD vs every active domain CV, pick the
        # best (best_domain_cv_id + s1d + domain_cv_scores), then compute domain ATS/Pursuit.
        # Idempotent (ats_domain IS NULL). No domain CV → clean no-op.
        domain_scored = 0
        if key:
            from app.models.cv import DomainCV, CVStatus
            from app.agents.scanner_agents import batch_score_s1
            from app.agents.rag_scorer import _essence_text
            dcv_rows = (await session.execute(
                select(DomainCV.id, DomainCV.content_md, DomainCV.essence_json)
                .where(DomainCV.user_id == uid, DomainCV.status == CVStatus.active,
                       DomainCV.content_md.isnot(None)))).all()
            domain_cvs = [{"id": str(did), "content_md": c, "essence": e} for did, c, e in dcv_rows]
            if domain_cvs:
                djobs = (await session.execute(select(Job).where(
                    Job.user_id == uid, Job.jd_raw.isnot(None), Job.ats_domain.is_(None)))).scalars().all()
                inputs = [{"id": str(j.id), "role": j.role or "", "company": j.company or "",
                           "location": j.location or "", "description": (j.jd_md or j.jd_raw or "")[:500]}
                          for j in djobs]
                # S1 vs each domain CV (batched), collect per-job scores → pick best.
                per_job = {str(j.id): {} for j in djobs}
                for dcv in domain_cvs:
                    dtext = _essence_text(dcv.get("essence")) or dcv.get("content_md", "")
                    if not dtext or not inputs:
                        continue
                    for s in await batch_score_s1(dtext, inputs, api_key=key):
                        if s.get("s1_score") is not None:
                            per_job[str(s["id"])][dcv["id"]] = s["s1_score"]
                dcv_by_id = {d["id"]: d for d in domain_cvs}
                for job in djobs:
                    try:
                        valid = {k: v for k, v in per_job.get(str(job.id), {}).items() if v is not None}
                        best = max(valid, key=valid.get) if valid else None
                        if best is None:
                            continue
                        job.domain_cv_scores = valid or None
                        job.best_domain_cv_id = _uuid.UUID(best)
                        job.s1d = valid.get(best)
                        d = dcv_by_id.get(best)
                        await compute_dual_scores(
                            d.get("essence") or (master.essence_json if master else {}),
                            d.get("content_md") or "", job.jd_md or job.jd_raw or "",
                            "domain", job=job, anthropic_key=key, session=session)
                        domain_scored += 1
                        await asyncio.sleep(0.2)  # ~5 jobs/sec rate limit
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"domain backfill score failed for job {job.id}: {e}")

        cost = round(get_session_usage().get("cost_inr", 0.0) - cost0, 2)
        run_log.status = RunStatus.success
        run_log.jobs_added = scored + domain_scored
        run_log.details = {"backfill": True, "jobs_scored": scored,
                           "domain_jobs_scored": domain_scored, "cost_inr": cost}
        run_log.completed_at = datetime.now(timezone.utc)
        run_log.duration_seconds = (run_log.completed_at - run_log.started_at).total_seconds()
        await session.commit()
    logger.warning(f"dual-score backfill: master {scored} · domain {domain_scored} jobs · ₹{cost}")
    return {"scored": scored, "cost_inr": cost}


@celery_app.task(name="tasks.score_pending_jobs_batch", bind=True)
def score_pending_jobs_batch(self):
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_batch_async())
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


async def _batch_async():
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials, UserPreferences
    from app.models.admin import RunLog, RunType, RunStatus
    from app.utils.encryption import decrypt_if_present
    from app.config import settings

    async with AsyncSessionLocal() as session:
        run_log = RunLog(run_type=RunType.night_batch, status=RunStatus.running,
                         started_at=datetime.now(timezone.utc))
        session.add(run_log)
        await session.flush()

        rows = (await session.execute(
            select(User, UserCredentials, UserPreferences)
            .join(UserCredentials, UserCredentials.user_id == User.id)
            .join(UserPreferences, UserPreferences.user_id == User.id)
            .where(User.is_active == True, UserPreferences.scoring_timing == "overnight"))).all()

        total_scored, total_cost, total_tokens, errors = 0, 0.0, 0, []
        for user, creds, prefs in rows:
            try:
                key = (decrypt_if_present(creds.anthropic_api_key_enc) if creds.anthropic_api_key_enc else None) \
                    or settings.platform_anthropic_api_key or settings.anthropic_api_key
                if not key:
                    continue
                r = await score_pending_for_user(user, session, key, prefs)
                total_scored += r["scored"]
                total_cost = round(total_cost + r["cost_inr"], 2)
                total_tokens += r["tokens"]
            except Exception as e:  # noqa: BLE001
                errors.append(f"{user.email}: {e}")
                logger.warning(f"night batch failed for {user.email}: {e}")

        run_log.status = RunStatus.success if not errors else RunStatus.partial
        run_log.jobs_added = total_scored
        run_log.details = {"users": len(rows), "jobs_scored": total_scored,
                           "cost_inr": total_cost, "tokens": total_tokens}
        run_log.completed_at = datetime.now(timezone.utc)
        run_log.duration_seconds = (run_log.completed_at - run_log.started_at).total_seconds()
        if errors:
            run_log.error_message = "; ".join(errors[:5])
        await session.commit()

    logger.warning(f"night batch: scored {total_scored} jobs · ₹{total_cost}")
    return {"scored": total_scored, "cost_inr": total_cost}

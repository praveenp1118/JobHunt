"""
One-time full data refresh for the owner account: recompute CV essence, backfill
ATS + Pursuit dual scores for all scored jobs, and invalidate the career / JD-highlights
caches. Idempotent — safe to run multiple times (skips work already done).

Run:
  docker-compose exec backend python -c \
    "import asyncio; from app.scripts.backfill_all import run_full_backfill; asyncio.run(run_full_backfill())"
"""
import asyncio
from datetime import datetime, timezone

OWNER_EMAIL = "praveenp.1118@gmail.com"
BATCH = 5          # commit + rate-limit cadence
SLEEP = 0.2        # ~5 jobs/sec


def _p(msg):
    print(msg, flush=True)


async def run_full_backfill(email: str = OWNER_EMAIL):
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials
    from app.models.cv import MasterCV, DomainCV
    from app.models.domain import IndustryVertical, FunctionalDiscipline
    from app.models.job import Job
    from app.models.career import CareerAnalysis
    from app.utils.encryption import decrypt_if_present
    from app.utils.usage_logger import set_usage_user, get_session_usage
    from app.agents.essence_agent import extract_cv_essence
    from app.agents.dual_scorer import compute_dual_scores
    from app.config import settings

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            _p(f"❌ User {email} not found"); return
        set_usage_user(user.id)

        creds = (await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id))).scalar_one_or_none()
        key = (decrypt_if_present(creds.anthropic_api_key_enc) if creds and creds.anthropic_api_key_enc else None) \
            or settings.platform_anthropic_api_key or settings.anthropic_api_key
        if not key:
            _p("❌ API key error — check Settings → Plan & Keys. Stopping."); return

        # ── STEP 1: CV essence ──────────────────────────────────────────────
        _p("━━━ STEP 1: CV essence ━━━")
        master = (await session.execute(
            select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
        if not master or not master.content_md:
            _p("❌ No active master CV with content — cannot score. Stopping."); return

        if not master.essence_json:
            try:
                master.essence_json = await extract_cv_essence(master.content_md, master.version, anthropic_key=key)
                master.essence_computed_at = datetime.now(timezone.utc)
                await session.commit()
                _p("  Master CV essence: computed")
            except Exception as e:  # noqa: BLE001
                _p(f"❌ Master essence extraction failed: {e}. Stopping."); return
        else:
            _p("  Master CV essence: already present (skipped)")
        master_essence = master.essence_json
        _p(f"  Master CV essence: {len(master_essence.get('keywords') or [])} keywords")

        dcvs = (await session.execute(select(DomainCV).where(DomainCV.user_id == user.id))).scalars().all()
        dcv_computed = 0
        for dcv in dcvs:
            if dcv.essence_json:
                dcv_computed += 1
                continue
            if not dcv.content_md:
                continue
            try:
                ind = (await session.execute(
                    select(IndustryVertical.label).where(IndustryVertical.id == dcv.industry_id))).scalar() if dcv.industry_id else None
                fn = (await session.execute(
                    select(FunctionalDiscipline.label).where(FunctionalDiscipline.id == dcv.function_id))).scalar() if dcv.function_id else None
                dcv.essence_json = await extract_cv_essence(
                    dcv.content_md, dcv.version,
                    domain_context={"industry": ind, "function": fn, "country_code": dcv.country_code},
                    anthropic_key=key)
                dcv.essence_computed_at = datetime.now(timezone.utc)
                await session.commit()
                dcv_computed += 1
            except Exception as e:  # noqa: BLE001
                _p(f"  ⚠️ Domain CV {dcv.id} essence failed: {e}")
        _p(f"  Domain CVs with essence: {dcv_computed}/{len(dcvs)}")
        dcv_map = {d.id: d for d in dcvs}

        # ── STEP 2: backfill ATS + Pursuit ──────────────────────────────────
        _p("━━━ STEP 2: backfill ATS + Pursuit ━━━")
        # Exclude partial-JD jobs (LinkedIn snippets are too short to score reliably).
        jobs = (await session.execute(select(Job).where(
            Job.user_id == user.id, Job.jd_raw.isnot(None), Job.ats_master.is_(None),
            Job.has_partial_jd.isnot(True), func.length(Job.jd_raw) >= 200))).scalars().all()
        total = len(jobs)
        _p(f"  {total} jobs to score (idempotent; partial-JD / <200-char snippets skipped)")
        cost0 = get_session_usage().get("cost_inr", 0.0)
        scored = failed = domain_scored = 0
        for i, job in enumerate(jobs, 1):
            jd = job.jd_md or job.jd_raw or ""
            try:
                await compute_dual_scores(master_essence, master.content_md, jd, "master",
                                          job=job, anthropic_key=key, session=None)
                scored += 1
                if job.best_domain_cv_id and job.best_domain_cv_id in dcv_map:
                    d = dcv_map[job.best_domain_cv_id]
                    await compute_dual_scores(d.essence_json or master_essence, d.content_md or "", jd,
                                              "domain", job=job, anthropic_key=key, session=None)
                    domain_scored += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                _p(f"  ⚠️ Failed job {job.id}: {e}")
            if i % BATCH == 0:
                await session.commit()
                await asyncio.sleep(SLEEP)
            if i % 25 == 0:
                spent = round(get_session_usage().get("cost_inr", 0.0) - cost0, 2)
                _p(f"  Scored {i}/{total} jobs… ₹{spent} spent so far")
        await session.commit()
        spent = round(get_session_usage().get("cost_inr", 0.0) - cost0, 2)
        _p(f"  Backfill complete: {scored} scored ({domain_scored} domain), {failed} failed · ₹{spent}")

        # ── STEP 3: invalidate career analysis cache (force re-analyse on visit) ──
        _p("━━━ STEP 3: invalidate career cache ━━━")
        cas = (await session.execute(
            select(CareerAnalysis).where(CareerAnalysis.user_id == user.id))).scalars().all()
        for ca in cas:
            ca.expires_at = datetime.now(timezone.utc)
        await session.commit()
        _p(f"  {len(cas)} career analyses expired (user re-triggers on the page)")

        # ── STEP 4: clear stale JD highlights ──
        _p("━━━ STEP 4: clear JD highlights cache ━━━")
        cleared = 0
        for job in (await session.execute(select(Job).where(
                Job.user_id == user.id, Job.jd_highlights_json.isnot(None)))).scalars().all():
            job.jd_highlights_json = None
            cleared += 1
        await session.commit()
        _p(f"  {cleared} JD-highlight caches cleared")

        # ── STEP 5: verify ──
        _p("━━━ STEP 5: verify ━━━")
        row = (await session.execute(select(
            func.count(Job.id), func.count(Job.ats_master), func.count(Job.pursuit_master),
            func.count(Job.ats_domain), func.avg(Job.ats_master), func.avg(Job.pursuit_master),
            func.max(Job.ats_master), func.max(Job.pursuit_master),
        ).where(Job.user_id == user.id, Job.jd_raw.isnot(None)))).first()
        total_jobs, has_ats, has_pur, has_ats_dom, avg_ats, avg_pur, max_ats, max_pur = row
        all_jobs = (await session.execute(select(func.count(Job.id)).where(Job.user_id == user.id))).scalar()
        no_jd = all_jobs - total_jobs

        top = (await session.execute(select(Job).where(
            Job.user_id == user.id, Job.pursuit_master.isnot(None))
            .order_by(Job.pursuit_master.desc()).limit(5))).scalars().all()

        def _r(v):
            return round(float(v), 1) if v is not None else None

        # ── STEP 7: report ──
        top_job = top[0] if top else None
        _p("\n┌─────────────────────────────────────────────────────────┐")
        _p("│ JobHunt Data Refresh Complete                           │")
        _p("├─────────────────────────────────────────────────────────┤")
        _p(f"│ CV Essence — Master: {len(master_essence.get('keywords') or [])} keywords · Domain CVs: {dcv_computed}/{len(dcvs)}")
        _p(f"│ Jobs — total: {all_jobs} · with JD: {total_jobs} · no JD (partial): {no_jd}")
        _p(f"│ Scored — ATS(master): {has_ats} · Pursuit(master): {has_pur} · ATS(domain): {has_ats_dom}")
        _p(f"│ Avg ATS: {_r(avg_ats)} · Avg Pursuit: {_r(avg_pur)} · Max ATS: {_r(max_ats)} · Max Pursuit: {_r(max_pur)}")
        if top_job:
            _p(f"│ Top by Pursuit: {top_job.company} · {top_job.role[:40]} (ATS {_r(top_job.ats_master)} / Pur {_r(top_job.pursuit_master)})")
        _p(f"│ This run: {scored} scored, {failed} failed · ₹{spent}")
        _p("├─────────────────────────────────────────────────────────┤")
        _p("│ Top 5 by Pursuit:")
        for j in top:
            _p(f"│   {(j.company or '')[:22]:24} {(j.role or '')[:30]:32} ATS {_r(j.ats_master)} / Pur {_r(j.pursuit_master)}")
        _p("├─────────────────────────────────────────────────────────┤")
        _p("│ Next: Career Insights → Re-analyse · Dashboard score card · hover a Match pill")
        _p("└─────────────────────────────────────────────────────────┘")
        return {"scored": scored, "failed": failed, "cost_inr": spent,
                "avg_ats": _r(avg_ats), "avg_pursuit": _r(avg_pur)}

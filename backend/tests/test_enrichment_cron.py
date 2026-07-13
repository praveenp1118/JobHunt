"""Daily auto-enrich cron (tasks.enrich_high_scoring_partials).

Verifies the query (opt-in + high-score threshold + enrichable + cap) and that it reuses
the existing enrich path (brightdata_collect_by_url -> rescore_partial_job_from_text),
both mocked so there are no real Claude/Bright-Data calls."""
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.utils.encryption import encrypt


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def _mock_enrich_path(monkeypatch):
    """brightdata_collect_by_url -> a full JD; rescore -> flips has_partial_jd false."""
    import app.utils.brightdata_client as bd
    import app.agents.gmail_alert_agent as ga

    async def fake_collect(url, sub_source, token, **k):
        return {"job_description_formatted": "Full JD. " * 40}
    monkeypatch.setattr(bd, "brightdata_collect_by_url", fake_collect)

    async def fake_rescore(job_id, user, session, anthropic_key, model=None):
        from app.models.job import Job
        j = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        j.has_partial_jd = False        # what the real rescore does (+ scores s1/s1d/dual)
        await session.commit()
        return {"status": "scored", "job_id": str(job_id)}
    monkeypatch.setattr(ga, "rescore_partial_job_from_text", fake_rescore)


async def _seed_user(S, uid, *, opted_in, threshold=70, has_bd, has_anthropic=True):
    from app.models.user import User, UserCredentials, UserPreferences
    async with S() as s:
        s.add(User(id=uid, email=f"e-{uid}@t.co", hashed_password="x", is_active=True,
                   is_superuser=False, is_verified=True, name="E"))
        await s.commit()
    async with S() as s:
        s.add(UserCredentials(
            user_id=uid,
            brightdata_token_enc=encrypt("bd-fake") if has_bd else None,
            anthropic_api_key_enc=encrypt("sk-fake") if has_anthropic else None))
        s.add(UserPreferences(user_id=uid, auto_enrich_partials=opted_in,
                              auto_enrich_threshold=threshold))
        await s.commit()


async def _add_job(S, uid, jid, *, s1=None, s1d=None, url, partial=True):
    from app.models.job import Job, JobSource, JobStatus
    async with S() as s:
        s.add(Job(id=jid, user_id=uid, company="Acme", role="Head of Product",
                  has_partial_jd=partial, s1=s1, s1d=s1d, portal_url=url,
                  jd_raw="stub", jd_md="stub", dedup_key=f"url:test/{jid}",
                  source=JobSource.gmail_alert, status=JobStatus.new))
        await s.commit()


async def _run_cron():
    from app.database import engine as _mod_engine
    from app.tasks.enrichment_tasks import _enrich_async
    await _mod_engine.dispose()        # bind the module pool to THIS test loop
    return await _enrich_async()


async def test_enrich_cron_targets_only_the_right_jobs(monkeypatch):
    """Opted-in + token + high-score + enrichable → enriched. Low-score, non-LinkedIn/Indeed,
    no-token, and opted-out are all skipped."""
    _mock_enrich_path(monkeypatch)
    from app.models.job import Job

    eng, S = _sm()
    uA, uB, uC = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a1, a2, a3, b1, c1 = (uuid.uuid4() for _ in range(5))
    try:
        await _seed_user(S, uA, opted_in=True, has_bd=True)
        await _seed_user(S, uB, opted_in=True, has_bd=False)          # no BD token
        await _seed_user(S, uC, opted_in=False, has_bd=True)          # opted out
        await _add_job(S, uA, a1, s1d=85, url="https://www.linkedin.com/jobs/view/1")   # ENRICH
        await _add_job(S, uA, a2, s1=40, url="https://www.linkedin.com/jobs/view/2")    # below threshold
        await _add_job(S, uA, a3, s1d=90, url="https://boards.greenhouse.io/x/jobs/3")  # not enrichable
        await _add_job(S, uB, b1, s1d=90, url="https://www.linkedin.com/jobs/view/4")   # no token → skip user
        await _add_job(S, uC, c1, s1d=90, url="https://www.linkedin.com/jobs/view/5")   # opted out → skip user

        res = await _run_cron()
        assert res["enriched"] == 1

        async with S() as s:
            flags = {str(j.id): j.has_partial_jd
                     for j in (await s.execute(select(Job).where(
                         Job.user_id.in_([uA, uB, uC])))).scalars().all()}
        assert flags[str(a1)] is False     # enriched
        assert flags[str(a2)] is True      # below threshold → untouched
        assert flags[str(a3)] is True      # not LinkedIn/Indeed → untouched
        assert flags[str(b1)] is True      # user has no BD token → skipped
        assert flags[str(c1)] is True      # user opted out → skipped
    finally:
        async with S() as s:
            for uid in (uA, uB, uC):
                await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
                await s.execute(text("DELETE FROM user_preferences WHERE user_id=:u"), {"u": str(uid)})
                await s.execute(text("DELETE FROM user_credentials WHERE user_id=:u"), {"u": str(uid)})
                await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()


async def test_enrich_cron_caps_per_user(monkeypatch):
    """More high-scoring partials than the cap → exactly `cap` enriched, best-first."""
    _mock_enrich_path(monkeypatch)
    monkeypatch.setattr(settings, "partial_enrich_cap", 3)
    from app.models.job import Job

    eng, S = _sm()
    uid = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(8)]
    try:
        await _seed_user(S, uid, opted_in=True, has_bd=True)
        for i, jid in enumerate(ids):
            await _add_job(S, uid, jid, s1d=71 + i,       # scores 71..78, all >= 70
                           url=f"https://www.linkedin.com/jobs/view/{i}")
        res = await _run_cron()
        assert res["enriched"] == 3                       # hard cap enforced

        async with S() as s:
            enriched_scores = sorted(
                (j.s1d for j in (await s.execute(select(Job).where(
                    Job.user_id == uid, Job.has_partial_jd == False))).scalars().all()),
                reverse=True)
        assert enriched_scores == [78, 77, 76]            # top-3 by score got enriched
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM user_preferences WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM user_credentials WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()

"""Night-batch scoring tests — pending status, batch scoring, score-now, defaults."""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _mk_user(session):
    from app.models.user import User
    uid = uuid.uuid4()
    session.add(User(id=uid, email=f"nb_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False))
    await session.flush()
    return uid


class FakeScorer:
    def __init__(self, score):
        self.score = score
    async def __call__(self, cv_text, jobs, batch_size=5, api_key=None, model=None):
        return [{"id": j["id"], "s1_score": self.score, "key_matches": [], "gaps": []} for j in jobs]


# ── Pending status exposed + not scored ──
async def test_pending_jobs_not_scored_in_overnight_mode(client, user_creds):
    from app.models.user import User
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    try:
        uid = uuid.UUID((await client.get("/api/auth/me", headers=user_creds["headers"])).json()["id"])
        jid = uuid.uuid4()
        async with S() as s:
            s.add(Job(id=jid, user_id=uid, company="ZZ", role="PM", market="NL",
                      source=JobSource.rss, status=JobStatus.new, jd_raw="x", jd_md="x",
                      s1=None, scoring_status="pending"))
            await s.commit()
        r = await client.get("/api/jobs?limit=200", headers=user_creds["headers"])
        job = next((j for j in r.json()["jobs"] if j["id"] == str(jid)), None)
        assert job is not None and job["scoring_status"] == "pending" and job["s1"] is None
        st = await client.get("/api/jobs/stats", headers=user_creds["headers"])
        assert st.json()["pending_count"] >= 1
    finally:
        await eng.dispose()


# ── Night batch scores all pending (monkeypatched scorer) ──
async def test_night_batch_scores_all_pending(monkeypatch):
    from app.models.cv import MasterCV
    from app.models.job import Job, JobSource, JobStatus
    from app.tasks.scoring_tasks import score_pending_for_user
    from app.models.user import User
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", FakeScorer(80))
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            s.add(MasterCV(user_id=uid, content_md="# CV", version=1, is_active=True,
                           essence_json={"keywords": ["python", "product", "ai"]}))
            for i in range(2):
                s.add(Job(id=uuid.uuid4(), user_id=uid, company=f"C{i}", role="PM", market="NL",
                          source=JobSource.rss, status=JobStatus.new,
                          jd_raw="python product ai role", jd_md="python product ai role",
                          s1=None, scoring_status="pending"))
            await s.commit()

            r = await score_pending_for_user(user, s, "fake-key", None)
            assert r["scored"] == 2
            jobs = (await s.execute(select(Job).where(Job.user_id == uid))).scalars().all()
            assert all(j.scoring_status == "scored" and j.s1 == 80 for j in jobs)

            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
    finally:
        await eng.dispose()


# ── Score-now endpoint wiring (already-scored path — no Claude) ──
async def test_score_now_endpoint_scores_single_job(client, active_user_creds):
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    try:
        uid = uuid.UUID((await client.get("/api/auth/me", headers=active_user_creds["headers"])).json()["id"])
        jid = uuid.uuid4()
        async with S() as s:
            s.add(Job(id=jid, user_id=uid, company="ZZ", role="PM", market="NL",
                      source=JobSource.rss, status=JobStatus.new, jd_raw="x", jd_md="x",
                      s1=77, scoring_status="scored"))
            await s.commit()
        # Already scored → no-op (no Claude call), returns the existing score.
        r = await client.post(f"/api/jobs/{jid}/score-now", headers=active_user_creds["headers"])
        assert r.status_code == 200 and r.json().get("already_scored") is True and r.json()["s1"] == 77
    finally:
        await eng.dispose()


# ── Defaults: immediate + scored ──
async def test_immediate_mode_scores_on_save(client, user_creds):
    # Fresh prefs default to "immediate"; jobs default to scoring_status="scored".
    cfg = await client.get("/api/scoring/config", headers=user_creds["headers"])
    assert cfg.json()["scoring_timing"] == "immediate"
    from app.models.user import UserPreferences
    eng, S = _sm()
    try:
        uid = uuid.UUID((await client.get("/api/auth/me", headers=user_creds["headers"])).json()["id"])
        async with S() as s:
            p = (await s.execute(select(UserPreferences).where(UserPreferences.user_id == uid))).scalars().first()
            assert p is None or p.scoring_timing == "immediate"
    finally:
        await eng.dispose()

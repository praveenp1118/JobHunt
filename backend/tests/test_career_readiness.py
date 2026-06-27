"""Career Insights readiness — real aggregated ATS + Pursuit scores."""
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def _components(ats_kw=30, pur_he=40):
    """A full score_components blob (master entity) with the given keyword_density / human_excitement."""
    return {"master": {
        "ats": {"components": {
            "keyword_density": {"score": ats_kw}, "required_skills": {"score": 25},
            "experience_years": {"score": 20}, "seniority_alignment": {"score": 15},
            "education": {"score": 10}}, "total": 90},
        "pursuit": {"components": {
            "human_excitement": {"score": pur_he}, "career_move_quality": {"score": 25},
            "achievability": {"score": 20}, "effort_reward": {"score": 15}}, "total": 80},
    }}


async def _add_job(session, uid, ats=85, pur=80, market="NL", feed_id=None, ats_kw=30, pur_he=40):
    from app.models.job import Job, JobSource, JobStatus
    session.add(Job(id=uuid.uuid4(), user_id=uid, company="C", role="PM", market=market,
                    source=JobSource.rss, status=JobStatus.new, jd_raw="x",
                    ats_master=ats, pursuit_master=pur, source_feed_id=feed_id,
                    score_components=_components(ats_kw, pur_he)))


async def _uid(client, user_creds):
    return uuid.UUID((await client.get("/api/auth/me", headers=user_creds["headers"])).json()["id"])


async def test_readiness_returns_no_data_when_unscored(client, user_creds):
    r = await client.get("/api/career/readiness-scores", headers=user_creds["headers"])
    body = r.json()
    assert body.get("no_data") is True and body.get("jobs_scored") == 0


async def test_ats_components_normalized_to_100(client, user_creds):
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds)
        async with S() as s:
            await _add_job(s, uid, ats_kw=30)   # 30/30 → 100%
            await s.commit()
        body = (await client.get("/api/career/readiness-scores", headers=user_creds["headers"])).json()
        assert body["ats"]["components"]["keyword_density"]["score"] == 100
        assert body["ats"]["components"]["education"]["score"] == 100  # 10/10
    finally:
        await eng.dispose()


async def test_pursuit_components_normalized_to_100(client, user_creds):
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds)
        async with S() as s:
            await _add_job(s, uid, pur_he=40)   # 40/40 → 100%
            await s.commit()
        body = (await client.get("/api/career/readiness-scores", headers=user_creds["headers"])).json()
        assert body["pursuit"]["components"]["human_excitement"]["score"] == 100
        assert body["pursuit"]["components"]["effort_reward"]["score"] == 100  # 15/15
    finally:
        await eng.dispose()


async def test_readiness_scores_aggregates_correctly(client, user_creds):
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds)
        async with S() as s:
            await _add_job(s, uid, ats=80, pur=60, ats_kw=30)   # kw 30/30=100
            await _add_job(s, uid, ats=60, pur=80, ats_kw=15)   # kw 15/30=50
            await s.commit()
        body = (await client.get("/api/career/readiness-scores", headers=user_creds["headers"])).json()
        assert body["jobs_scored"] == 2
        assert body["avg_ats"] == 70 and body["avg_pursuit"] == 70          # (80+60)/2, (60+80)/2
        assert body["ats"]["components"]["keyword_density"]["score"] == 75  # (100+50)/2
        assert body["overall"] == round(70 * 0.4 + 70 * 0.6)               # 70
    finally:
        await eng.dispose()


async def test_readiness_filters_by_market(client, user_creds):
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds)
        async with S() as s:
            await _add_job(s, uid, market="NL", ats=90)
            await _add_job(s, uid, market="SG", ats=40)
            await s.commit()
        nl = (await client.get("/api/career/readiness-scores?market=NL", headers=user_creds["headers"])).json()
        assert nl["jobs_scored"] == 1 and nl["avg_ats"] == 90
    finally:
        await eng.dispose()


async def test_readiness_filters_by_feed(client, user_creds):
    from app.models.domain import UserFeed
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds)
        fid = uuid.uuid4()
        async with S() as s:
            s.add(UserFeed(id=fid, user_id=uid, feed_type="rss", name="F", url_or_actor="http://x", is_active=True))
            await s.flush()
            await _add_job(s, uid, feed_id=fid, ats=88)
            await _add_job(s, uid, feed_id=None, ats=44)
            await s.commit()
        r = (await client.get(f"/api/career/readiness-scores?feed_id={fid}", headers=user_creds["headers"])).json()
        assert r["jobs_scored"] == 1 and r["avg_ats"] == 88
    finally:
        await eng.dispose()

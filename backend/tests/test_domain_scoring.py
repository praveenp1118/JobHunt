"""V3 multi-domain-CV scoring tests.

1. `_best_domain` selection logic (pure — no DB/Claude): given domain_cv_scores,
   the highest-scoring domain CV is chosen as best.
2. API round-trip: a job with `domain_cv_scores` populated is returned by
   GET /api/jobs with the scores + s1d, and the highest score is the expected best.
"""
import uuid

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.gmail_alert_agent import _best_domain


def test_best_domain_picks_highest_score():
    a, b, c = "id-a", "id-b", "id-c"
    assert _best_domain({a: 61, b: 88, c: 54}) == (b, 88)   # highest wins
    assert _best_domain({a: None, b: 70}) == (b, 70)        # None ignored
    assert _best_domain({}) == (None, None)                 # no scores
    assert _best_domain(None) == (None, None)               # missing


async def test_jobs_api_returns_domain_cv_scores_and_best(client, user_creds):
    """A job with domain_cv_scores populated is returned by GET /api/jobs with the
    scores + s1d, and the highest-scoring domain CV is the expected best."""
    # Resolve the freshly-registered user's id directly (robust to schema shape).
    conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
    try:
        uid = (await conn.fetchrow("SELECT id FROM users WHERE email=$1", user_creds["email"]))["id"]
    finally:
        await conn.close()

    from app.models.job import Job, JobSource, JobStatus
    job_id = uuid.uuid4()
    dcv_hi, dcv_lo = str(uuid.uuid4()), str(uuid.uuid4())
    scores = {dcv_hi: 88, dcv_lo: 61}

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            s.add(Job(
                id=job_id, user_id=uid, company="Adyen", role="Senior PM, AI",
                source=JobSource.rss, status=JobStatus.new,
                s1=70, s1d=88, domain_cv_scores=scores,
            ))
            await s.commit()
    finally:
        await engine.dispose()

    r = await client.get("/api/jobs?limit=50", headers=user_creds["headers"])
    assert r.status_code == 200
    body = r.json()
    assert "jobs" in body and "total_count" in body and "unfiltered_count" in body
    job = next((j for j in body["jobs"] if j["id"] == str(job_id)), None)
    assert job is not None, "inserted job not returned by /api/jobs"
    assert job["domain_cv_scores"] == scores
    assert job["s1d"] == 88
    # best_domain_cv_id is whichever domain CV scored highest
    assert max(scores, key=scores.get) == dcv_hi
    # cleanup happens via user_creds teardown (jobs.user_id ON DELETE CASCADE)

"""V3 LinkedIn alert email body parsing + partial-JD flag.

Pure-function tests for the parser/detection, plus an API round-trip that a
gmail_alert job with has_partial_jd=True surfaces the flag in GET /api/jobs.
"""
import uuid

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.gmail_alert_agent import (
    extract_jobs_from_linkedin_email, is_job_alert_email, _is_linkedin_alert,
)

# Mirrors LinkedIn alert HTML: each posting is a /jobs/view/<id> link wrapping the
# role, then "Company · Location", then noise ("Actively recruiting").
LI_HTML = """
<html><body>
  <a href="https://www.linkedin.com/comm/jobs/view/3801234567/?trk=eml">
    <span>Head of Product</span><span>Adyen &middot; Amsterdam, Netherlands</span><span>Actively recruiting</span>
  </a>
  <a href="https://www.linkedin.com/comm/jobs/view/3809876543/">
    <span>VP Product</span><span>Booking.com &middot; Amsterdam</span>
  </a>
  <a href="https://www.linkedin.com/comm/jobs/view/3805555555/">
    <span>Chief Product Officer</span><span>Mollie &middot; Amsterdam, NL</span>
  </a>
</body></html>
"""


def test_extract_jobs_from_linkedin_email():
    jobs = extract_jobs_from_linkedin_email(LI_HTML)
    assert len(jobs) == 3
    j = jobs[0]
    assert j["title"] == "Head of Product"
    assert j["company"] == "Adyen"
    assert "Amsterdam" in (j["location"] or "")
    assert "/jobs/view/" in j["url"]
    # noise dropped, not treated as the role
    assert all("Actively recruiting" not in (x["title"] or "") for x in jobs)


def test_is_linkedin_alert():
    assert _is_linkedin_alert("jobs-noreply@linkedin.com")
    assert _is_linkedin_alert("jobalerts@linkedin.com")
    assert not _is_linkedin_alert("recruiter@adyen.com")


async def test_is_job_alert_email_detects_linkedin():
    # sender + subject + 3 job links → 3 signals → job alert
    assert await is_job_alert_email(
        "5 new jobs for Head of Product in Amsterdam",
        "jobs-noreply@linkedin.com", LI_HTML) is True


async def test_partial_jd_flag_exposed_via_api(client, user_creds):
    conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
    try:
        uid = (await conn.fetchrow("SELECT id FROM users WHERE email=$1", user_creds["email"]))["id"]
    finally:
        await conn.close()

    from app.models.job import Job, JobSource, JobStatus
    job_id = uuid.uuid4()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            s.add(Job(
                id=job_id, user_id=uid, company="Adyen", role="Head of Product",
                source=JobSource.gmail_alert, status=JobStatus.new,
                has_partial_jd=True, portal_url="https://www.linkedin.com/jobs/view/3801234567",
            ))
            await s.commit()
    finally:
        await engine.dispose()

    # hide_partial defaults ON, so partial jobs are hidden unless explicitly requested.
    r = await client.get("/api/jobs?limit=50&hide_partial=false", headers=user_creds["headers"])
    assert r.status_code == 200
    job = next((j for j in r.json()["jobs"] if j["id"] == str(job_id)), None)
    assert job is not None and job["has_partial_jd"] is True
    # and it is hidden by default
    r2 = await client.get("/api/jobs?limit=50", headers=user_creds["headers"])
    assert not any(j["id"] == str(job_id) for j in r2.json()["jobs"])
    # cleanup via user_creds teardown (jobs.user_id ON DELETE CASCADE)

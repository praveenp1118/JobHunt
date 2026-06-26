"""Email to JobHunt — save a job URL by emailing it to your job-search Gmail."""
import uuid

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.gmail_alert_agent import (
    is_save_job_email, extract_first_url, process_save_job_email,
)


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _mk_user(session):
    from app.models.user import User
    uid = uuid.uuid4()
    session.add(User(id=uid, email=f"ej_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False))
    await session.flush()
    return uid


# ── Pure detection ──
def test_is_save_job_email():
    assert is_save_job_email("jh: Head of Product at Adyen") is True
    assert is_save_job_email("jt: Save this") is True
    assert is_save_job_email("Please add to jobhunt") is True
    assert is_save_job_email("track this job for me") is True
    assert is_save_job_email("Crawl this posting") is True
    assert is_save_job_email("Your weekly newsletter") is False
    assert is_save_job_email("") is False


# ── Pure URL extraction ──
def test_extract_first_url():
    assert extract_first_url('<a href="https://boards.greenhouse.io/acme/jobs/1">x</a>') == "https://boards.greenhouse.io/acme/jobs/1"
    # social/footer links are skipped, the real job link wins
    assert extract_first_url('<a href="https://facebook.com/x">fb</a> apply: https://lever.co/acme/abc') == "https://lever.co/acme/abc"
    assert extract_first_url("", "jh: https://jobs.lever.co/acme/xyz") == "https://jobs.lever.co/acme/xyz"
    assert extract_first_url("just text, no link", "jh: Head of Product at Adyen") is None


# ── Fetch + parse + score + save (mocked fetch/parse) ──
async def test_process_save_job_email_saves(monkeypatch):
    from app.models.user import User
    from app.models.job import Job, EmailThread, JobSource, JobStatus, EmailDirection, EmailClassification
    from app.models.admin import EmailAlertLog

    async def _fake_fetch(url):
        return "Head of Product job description. " * 30  # > 100 chars

    async def _fake_parse(content, master_cv_md, api_key, model=None):
        return {"s1_score": 78, "parsed": {"company": "Adyen", "role": "Head of Product",
                                           "location": "Amsterdam", "market": "NL"}}

    monkeypatch.setattr("app.agents.jd_agents.fetch_url_content", _fake_fetch)
    monkeypatch.setattr("app.agents.jd_agents.parse_and_score_jd", _fake_parse)

    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            thread = EmailThread(user_id=uid, direction=EmailDirection.received,
                                 classification=EmailClassification.save_job,
                                 subject="jh: save this", from_email="me@example.com")
            s.add(thread)
            await s.flush()

            res = await process_save_job_email(
                thread, '<a href="https://boards.greenhouse.io/acme/jobs/1">apply</a>',
                "jh: save this", user, s, "fake-key", None, None)
            await s.commit()

            assert res["action"] == "saved" and res["company"] == "Adyen" and res["s1"] == 78
            job = (await s.execute(select(Job).where(Job.user_id == uid))).scalar_one()
            assert job.source == JobSource.manual and job.status == JobStatus.new
            assert job.portal_url == "https://boards.greenhouse.io/acme/jobs/1" and job.s1 == 78
            assert job.source_email_id == thread.id
            # Activity log written with the email_to_jobhunt marker
            log = (await s.execute(select(EmailAlertLog).where(EmailAlertLog.user_id == uid))).scalar_one()
            assert log.jobs_saved == 1 and log.skip_reasons[0]["reason"] == "email_to_jobhunt"

            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
    finally:
        await eng.dispose()


# ── No URL in the email → no_url, nothing created ──
async def test_process_save_job_email_no_url():
    from app.models.user import User
    from app.models.job import Job, EmailThread, EmailDirection, EmailClassification
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            thread = EmailThread(user_id=uid, direction=EmailDirection.received,
                                 classification=EmailClassification.save_job,
                                 subject="jh: Head of Product at Adyen", from_email="me@example.com")
            s.add(thread)
            await s.flush()

            res = await process_save_job_email(
                thread, "no link in this body", "jh: Head of Product at Adyen",
                user, s, "fake-key", None, None)
            await s.commit()

            assert res["action"] == "no_url" and res["saved"] == 0
            assert (await s.execute(select(func.count(Job.id)).where(Job.user_id == uid))).scalar() == 0

            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
    finally:
        await eng.dispose()

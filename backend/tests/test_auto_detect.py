"""Auto-detect external applications from Gmail confirmation emails."""
import uuid

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.application_detector import extract_company_role, detect_external_application


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _mk_user(session):
    from app.models.user import User
    uid = uuid.uuid4()
    session.add(User(id=uid, email=f"ad_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False))
    await session.flush()
    return uid


class FakeEmail:
    def __init__(self, subject, from_email="jobs-noreply@linkedin.com", message_id=None, received_at=None):
        self.subject = subject
        self.from_email = from_email
        self.to_email = "me@example.com"
        self.message_id = message_id or f"m_{uuid.uuid4().hex[:8]}"
        self.received_at = received_at
    def body_preview(self, n=500):
        return ""


# ── Pure extraction ──
def test_extract_company_role():
    assert extract_company_role("Your application was sent to Tredence Inc.") == ("Tredence Inc", None)
    assert extract_company_role("You applied to Head of Product at Adyen") == ("Adyen", "Head of Product")
    assert extract_company_role("Application sent: Senior PM at Booking.com") == ("Booking.com", "Senior PM")
    assert extract_company_role("Indeed Application: Head of Product - Adyen") == ("Adyen", "Head of Product")
    assert extract_company_role("Thanks for applying to Stripe") == ("Stripe", None)
    # Non-confirmation subjects yield nothing.
    assert extract_company_role("10 new jobs for you") == (None, None)
    assert extract_company_role("") == (None, None)


# ── Match an existing new/bookmarked job → applied ──
async def test_auto_detect_matches_existing_job():
    from app.models.user import User
    from app.models.job import Job, EmailThread, JobStatus, JobSource
    from app.models.admin import EmailAlertLog
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            job = Job(user_id=uid, company="Adyen", role="PM", status=JobStatus.new, source=JobSource.rss)
            s.add(job)
            await s.flush()
            jid = job.id

            res = await detect_external_application(FakeEmail("You applied to Head of Product at Adyen"), user, s)
            await s.commit()

            assert res["action"] == "matched" and res["job_id"] == str(jid)
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.status == JobStatus.applied and j.applied_at is not None
            # Linking EmailThread + Activity log written
            assert (await s.execute(select(func.count(EmailThread.id)).where(EmailThread.job_id == jid))).scalar() == 1
            assert (await s.execute(select(func.count(EmailAlertLog.id)).where(EmailAlertLog.user_id == uid))).scalar() == 1

            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
    finally:
        await eng.dispose()


# ── No match → create a new applied job (source=gmail_alert) ──
async def test_auto_detect_creates_job_when_no_match():
    from app.models.user import User
    from app.models.job import Job, JobStatus, JobSource
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()

            res = await detect_external_application(FakeEmail("Your application was sent to Mollie"), user, s)
            await s.commit()

            assert res["action"] == "created"
            j = (await s.execute(select(Job).where(Job.user_id == uid))).scalar_one()
            assert j.company == "Mollie" and j.status == JobStatus.applied and j.source == JobSource.gmail_alert
            assert j.applied_at is not None

            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
    finally:
        await eng.dispose()


# ── Unparseable confirmation → no_company, nothing created ──
async def test_auto_detect_no_company_is_noop():
    from app.models.user import User
    from app.models.job import Job
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()

            res = await detect_external_application(FakeEmail("Your weekly digest is ready"), user, s)
            await s.commit()

            assert res["action"] == "no_company"
            assert (await s.execute(select(func.count(Job.id)).where(Job.user_id == uid))).scalar() == 0

            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
    finally:
        await eng.dispose()

"""Cross-source dedup — tiered dedup_key builder + ON CONFLICT single-save.

Builder tests are pure. The ON CONFLICT test runs in-process against the live DB and
skips if the UNIQUE index (migration v7_dedup_key_unique) isn't applied yet."""
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.utils.dedup import build_dedup_key


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


# ── builder: one test per tier ──────────────────────────────────────────────────
def test_dedup_key_tier1_linkedin_comm():
    # the email /comm/jobs/view tracking form canonicalises to the same job id
    assert build_dedup_key("X", "Y", "Z",
        "https://www.linkedin.com/comm/jobs/view/4432636617/?trackingId=abc&trk=eml-xyz"
        ) == "linkedin:4432636617"


def test_dedup_key_tier1_linkedin_plain():
    assert build_dedup_key("X", "Y", "Z",
        "https://www.linkedin.com/jobs/view/123") == "linkedin:123"


def test_dedup_key_tier1_indeed_jk():
    assert build_dedup_key("X", "Y", "Z",
        "https://nl.indeed.com/viewjob?jk=b661bc2362cab0c6") == "indeed:b661bc2362cab0c6"


def test_dedup_key_tier2_canonical_url():
    assert build_dedup_key("X", "Y", "Z",
        "https://boards.greenhouse.io/acme/jobs/999?utm=x"
        ) == "url:boards.greenhouse.io/acme/jobs/999"


def test_dedup_key_tier3_company_role_location():
    assert build_dedup_key("Booking.com", "Head of Product", "Amsterdam", None) == \
        "crl:booking com|head of product|amsterdam"


def test_dedup_key_cross_source_linkedin_collapses():
    """Same LinkedIn posting seen by Apify (plain URL) and Gmail (/comm tracking URL),
    with different company/title casing, collapses to ONE key."""
    apify = build_dedup_key("Booking", "Head of Product", "Amsterdam",
                            "https://www.linkedin.com/jobs/view/555")
    gmail = build_dedup_key("Booking.com", "Head of Product - AI", "Amsterdam, NL",
                            "https://www.linkedin.com/comm/jobs/view/555/?trk=eml-xyz")
    assert apify == gmail == "linkedin:555"


# ── ON CONFLICT collapses a duplicate insert ────────────────────────────────────
async def test_upsert_on_conflict_collapses_duplicate():
    from app.utils.dedup import upsert_job
    from app.models.job import Job, JobSource, JobStatus
    from app.models.user import User

    eng, S = _sm()
    async with eng.connect() as c:
        has_idx = (await c.execute(text(
            "SELECT 1 FROM pg_indexes WHERE indexname='uq_jobs_user_dedup'"))).first()
    if not has_idx:
        await eng.dispose()
        pytest.skip("uq_jobs_user_dedup not applied yet (run migration v7_dedup_key_unique)")

    uid = uuid.uuid4()
    vals = dict(user_id=uid, company="Acme", role="Head of Product", location="Amsterdam",
                portal_url="https://www.linkedin.com/jobs/view/999999",
                source=JobSource.gmail_alert, status=JobStatus.new, jd_raw="x", jd_md="x")
    try:
        async with S() as s:
            s.add(User(id=uid, email=f"dd-{uid}@t.co", hashed_password="x", is_active=True,
                       is_superuser=False, is_verified=True, name="DD"))
            await s.commit()
        async with S() as s:
            j1, c1 = await upsert_job(s, dict(vals))
            await s.commit()
        async with S() as s:
            j2, c2 = await upsert_job(s, dict(vals))   # same (user_id, dedup_key)
            await s.commit()
        assert c1 is True and c2 is False              # second was a no-op conflict
        assert j1.id == j2.id                          # existing row returned
        async with S() as s:
            n = (await s.execute(
                select(func.count()).select_from(Job).where(Job.user_id == uid))).scalar()
        assert n == 1                                  # exactly one row survived
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()

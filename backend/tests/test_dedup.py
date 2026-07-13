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


# ── Change 2: ON CONFLICT DO UPDATE enrich ──────────────────────────────────────
async def _seed_job(S, uid, jid, **overrides):
    from app.models.job import Job, JobSource, JobStatus
    from app.models.user import User
    async with S() as s:
        s.add(User(id=uid, email=f"c2-{uid}@t.co", hashed_password="x", is_active=True,
                   is_superuser=False, is_verified=True, name="C2"))
        await s.commit()
    vals = dict(id=jid, user_id=uid, company="Acme", role="Head of Product",
                dedup_key="url:example.com/job/1", portal_url="https://example.com/job/1",
                source=JobSource.gmail_alert, status=JobStatus.new)
    vals.update(overrides)
    async with S() as s:
        s.add(Job(**vals))
        await s.commit()


async def _cleanup_c2(S, uid):
    async with S() as s:
        await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
        await s.commit()


async def test_upsert_enriches_partial_to_full():
    """Existing PARTIAL + incoming FULL → jd enriched, has_partial_jd flips false, created=False."""
    from app.utils.dedup import upsert_job
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        await _seed_job(S, uid, jid, has_partial_jd=True, jd_raw="stub", jd_md="stub", s1=None)
        async with S() as s:
            job, created = await upsert_job(s, dict(
                user_id=uid, company="Acme", role="Head of Product",
                dedup_key="url:example.com/job/1", portal_url="https://example.com/job/1",
                jd_raw="FULL JD. " * 40, jd_md="FULL JD. " * 40, has_partial_jd=False,
                source=JobSource.rss, status=JobStatus.new))
            await s.commit()
        assert created is False
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.has_partial_jd is False
            assert (j.jd_raw or "").startswith("FULL JD")
    finally:
        await _cleanup_c2(S, uid)
        await eng.dispose()


async def test_upsert_no_downgrade_full_to_partial():
    """Existing FULL + incoming PARTIAL → NEVER downgrades (flag stays false, jd unchanged)."""
    from app.utils.dedup import upsert_job
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        await _seed_job(S, uid, jid, has_partial_jd=False, jd_raw="ORIGINAL FULL JD", jd_md="ORIGINAL FULL JD")
        async with S() as s:
            await upsert_job(s, dict(
                user_id=uid, company="Acme", role="Head of Product",
                dedup_key="url:example.com/job/1", portal_url="https://example.com/job/1",
                jd_raw="tiny", jd_md="tiny", has_partial_jd=True,
                source=JobSource.gmail_alert, status=JobStatus.new))
            await s.commit()
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.has_partial_jd is False and j.jd_raw == "ORIGINAL FULL JD"
    finally:
        await _cleanup_c2(S, uid)
        await eng.dispose()


async def test_upsert_never_touches_progress():
    """status / scores / notes are PROTECTED — never overwritten on conflict."""
    from app.utils.dedup import upsert_job
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        await _seed_job(S, uid, jid, has_partial_jd=True, jd_raw="stub", jd_md="stub",
                        status=JobStatus.applied, s1=88.0, s1d=91.0, notes="my private note")
        async with S() as s:
            await upsert_job(s, dict(
                user_id=uid, company="Acme", role="Head of Product",
                dedup_key="url:example.com/job/1", portal_url="https://example.com/job/1",
                jd_raw="FULL JD. " * 40, jd_md="FULL JD. " * 40, has_partial_jd=False,
                s1=10.0, s1d=10.0, status=JobStatus.new, notes="overwrite attempt",
                source=JobSource.rss))
            await s.commit()
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.status == JobStatus.applied        # untouched
            assert j.s1 == 88.0 and j.s1d == 91.0        # untouched
            assert j.notes == "my private note"          # untouched
            assert j.has_partial_jd is False             # but the JD WAS enriched
    finally:
        await _cleanup_c2(S, uid)
        await eng.dispose()


async def test_upsert_fill_if_null_respects_existing():
    """fill-if-null: existing non-null portal_url kept; existing NULL market filled."""
    from app.utils.dedup import upsert_job
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        # existing FULL, portal_url set, market NULL
        await _seed_job(S, uid, jid, has_partial_jd=False, jd_raw="full", jd_md="full",
                        portal_url="https://example.com/job/1", market=None)
        async with S() as s:
            await upsert_job(s, dict(
                user_id=uid, company="Acme", role="Head of Product",
                dedup_key="url:example.com/job/1", portal_url="https://OTHER.example.com/x",
                market="NL", jd_raw="full2", jd_md="full2", has_partial_jd=False,
                source=JobSource.rss, status=JobStatus.new))
            await s.commit()
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.portal_url == "https://example.com/job/1"   # non-null kept (not overwritten)
            assert j.market == "NL"                              # NULL filled
    finally:
        await _cleanup_c2(S, uid)
        await eng.dispose()

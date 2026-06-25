"""Community Insights tests — aggregation + privacy floor + endpoints."""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.utils.community import normalize_role, normalize_company, upsert_community_insights, get_community_insights

OWNER = uuid.UUID("fff12f28-0ee6-41df-85ad-490b1391c716")
CO = "ZZTestCo"
ROLE = "Head of Product - Test"


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def _changelog():
    return [
        SimpleNamespace(change_type="keyword_injection", status="approved",
                        proposed_text="connector ecosystem", final_text=None, original_text=None),
        SimpleNamespace(change_type="keyword_injection", status="rejected",
                        proposed_text="api-first platform", final_text=None, original_text=None),
        SimpleNamespace(change_type="rephrase", status="approved",
                        proposed_text="x", final_text=None, original_text=None),
    ]


async def _mk_user_job(session, s1, s1d):
    from app.models.user import User
    from app.models.job import Job, JobSource, JobStatus
    uid = uuid.uuid4()
    session.add(User(id=uid, email=f"ctest_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False))
    await session.flush()   # user must exist before the job FK
    job = Job(id=uuid.uuid4(), user_id=uid, company=CO, role=ROLE, market="NL",
              s1=s1, s1d=s1d, source=JobSource.manual, status=JobStatus.new, jd_raw="", jd_md="")
    session.add(job)
    await session.flush()
    return uid, job


async def _cleanup(session):
    await session.execute(text("delete from community_contributions"))
    # Insights store the normalized company key (e.g. "ZZTestCo" -> "zztestco").
    await session.execute(text("delete from community_job_insights where company = :c"),
                          {"c": normalize_company(CO)})
    await session.execute(text("delete from users where email like 'ctest_%'"))
    await session.commit()


# ── Pure ──
def test_normalize_role():
    assert normalize_role("Head of Product - AI/ML") == "head of product ai ml"
    assert normalize_role("  VP, Product  &  Growth ") == "vp product growth"


def test_normalize_company():
    # "Adyen" = "adyen" = "ADYEN" = "Adyen, Inc." collapse to one bucket key.
    assert normalize_company("Adyen") == "adyen"
    assert normalize_company("ADYEN") == "adyen"
    assert normalize_company("  Adyen, Inc. ") == "adyen inc"


# ── Aggregation + privacy ──
async def test_upsert_creates_insight():
    eng, S = _sm()
    try:
        async with S() as s:
            await _cleanup(s)
            uid, job = await _mk_user_job(s, 70, 80)
            iid = await upsert_community_insights(s, uid, job, None, _changelog())
            await s.commit()
            assert iid is not None
            from app.models.community import CommunityJobInsight
            ins = (await s.execute(select(CommunityJobInsight).where(CommunityJobInsight.id == iid))).scalar_one()
            assert ins.contributor_count == 1
            assert ins.avg_s1 == 70 and ins.avg_s1d == 80
            # one approved keyword_injection -> one keyword pattern
            kws = {k["keyword"] for k in (ins.keyword_patterns or [])}
            assert "connector ecosystem" in kws
            await _cleanup(s)
    finally:
        await eng.dispose()


async def test_upsert_merges_second_contributor():
    eng, S = _sm()
    try:
        async with S() as s:
            await _cleanup(s)
            u1, j1 = await _mk_user_job(s, 70, 80)
            await upsert_community_insights(s, u1, j1, None, _changelog())
            u2, j2 = await _mk_user_job(s, 90, 100)
            iid = await upsert_community_insights(s, u2, j2, None, _changelog())
            await s.commit()
            from app.models.community import CommunityJobInsight
            ins = (await s.execute(select(CommunityJobInsight).where(CommunityJobInsight.id == iid))).scalar_one()
            assert ins.contributor_count == 2
            assert ins.avg_s1 == 80 and ins.avg_s1d == 90  # running average
            await _cleanup(s)
    finally:
        await eng.dispose()


async def test_get_insights_returns_none_for_1_contributor():
    eng, S = _sm()
    try:
        async with S() as s:
            await _cleanup(s)
            u1, j1 = await _mk_user_job(s, 70, 80)
            await upsert_community_insights(s, u1, j1, None, _changelog())
            await s.commit()
            data = await get_community_insights(s, CO, ROLE)
            assert data is None  # privacy floor: < 2 contributors
            await _cleanup(s)
    finally:
        await eng.dispose()


async def test_get_insights_requires_2_contributors():
    eng, S = _sm()
    try:
        async with S() as s:
            await _cleanup(s)
            u1, j1 = await _mk_user_job(s, 70, 80)
            await upsert_community_insights(s, u1, j1, None, _changelog())
            u2, j2 = await _mk_user_job(s, 90, 100)
            await upsert_community_insights(s, u2, j2, None, _changelog())
            await s.commit()
            data = await get_community_insights(s, CO, ROLE)
            assert data is not None
            assert data["available"] is True and data["contributor_count"] == 2
            # internal _approved must not leak
            assert all("_approved" not in k for k in data["keyword_patterns"])
            await _cleanup(s)
    finally:
        await eng.dispose()


# ── Endpoints ──
async def test_share_endpoint_200(client):
    from app.auth.config import get_jwt_strategy
    from app.models.user import User
    from app.models.job import Job
    eng, S = _sm()
    try:
        async with S() as s:
            u = (await s.execute(select(User).where(User.id == OWNER))).scalar_one_or_none()
            if not u:
                pytest.skip("owner absent")
            tok = await get_jwt_strategy().write_token(u)
            job = (await s.execute(select(Job).where(Job.user_id == OWNER, Job.company.isnot(None)).limit(1))).scalar_one_or_none()
            if not job:
                pytest.skip("owner has no job")
            jid = job.id
        r = await client.post(f"/api/community/share/{jid}", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        assert r.json()["shared"] is True
        async with S() as s:
            await s.execute(text("delete from community_contributions"))
            await s.execute(text("delete from community_job_insights"))
            await s.commit()
    finally:
        await eng.dispose()


async def test_community_preferences_update(client, user_creds):
    r = await client.patch("/api/community/preferences",
                           json={"community_sharing_enabled": True}, headers=user_creds["headers"])
    assert r.status_code == 200
    assert r.json()["community_sharing_enabled"] is True
    g = await client.get("/api/auth/me/preferences", headers=user_creds["headers"])
    assert g.json().get("community_sharing_enabled") is True

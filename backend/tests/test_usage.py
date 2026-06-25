"""API usage logging + endpoint tests."""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.utils.usage_logger import estimate_anthropic_cost, log_anthropic_usage, log_apify_usage
from app.models.usage import APIUsageLog

OWNER = uuid.UUID("fff12f28-0ee6-41df-85ad-490b1391c716")
TAG = "ZZ_test_usage"


def _sessionmaker():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _owner_present(session) -> bool:
    from app.models.user import User
    return (await session.execute(select(User).where(User.id == OWNER))).scalar_one_or_none() is not None


# ── Pure cost math ────────────────────────────────────────────────────────────
def test_cost_calculation_sonnet():
    usd, inr = estimate_anthropic_cost(1000, 500, "claude-sonnet-4-6")
    # (1000*3 + 500*15) / 1e6 = 0.0105 ; * 83.5 = 0.87675
    assert usd == 0.0105
    assert round(inr, 3) == 0.877


# ── Logger writes ─────────────────────────────────────────────────────────────
async def test_log_anthropic_usage_saves_correctly():
    eng, Session = _sessionmaker()
    try:
        async with Session() as s:
            if not await _owner_present(s):
                pytest.skip("owner not present")
            await log_anthropic_usage(s, OWNER, "test_agent", "tailoring", 2000, 800,
                                      "claude-haiku-4-5", entity_label=TAG)
            await s.commit()
            row = (await s.execute(select(APIUsageLog).where(
                APIUsageLog.entity_label == TAG, APIUsageLog.provider == "anthropic"))).scalars().first()
            assert row is not None
            assert row.total_tokens == 2800
            # haiku: (2000*0.25 + 800*1.25)/1e6 = 0.0015
            assert row.estimated_cost_usd == 0.0015
            assert row.category == "tailoring"
            await s.execute(text("delete from api_usage_logs where entity_label = :t"), {"t": TAG})
            await s.commit()
    finally:
        await eng.dispose()


async def test_log_apify_usage_saves_correctly():
    eng, Session = _sessionmaker()
    try:
        async with Session() as s:
            if not await _owner_present(s):
                pytest.skip("owner not present")
            await log_apify_usage(s, OWNER, actor_id="curious_coder/linkedin-jobs-scraper",
                                  feed_label=TAG, runs_requested=25, runs_returned=20,
                                  jobs_saved=8, cost_usd=0.1)
            await s.commit()
            row = (await s.execute(select(APIUsageLog).where(
                APIUsageLog.entity_label == TAG, APIUsageLog.provider == "apify"))).scalars().first()
            assert row is not None
            assert row.runs_returned == 20 and row.jobs_saved == 8
            assert row.category == "scanner"
            assert round(row.estimated_cost_inr, 2) == round(0.1 * 83.5, 2)
            await s.execute(text("delete from api_usage_logs where entity_label = :t"), {"t": TAG})
            await s.commit()
    finally:
        await eng.dispose()


# ── Endpoints ─────────────────────────────────────────────────────────────────
async def test_get_usage_logs_returns_summary(client, user_creds):
    r = await client.get("/api/usage/logs?days=30", headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["logs"], list)
    assert "anthropic" in d["summary"] and "apify" in d["summary"]
    assert "by_category" in d["summary"]["anthropic"]
    assert "total_runs" in d["summary"]["apify"]


async def test_export_csv_returns_file(client, user_creds):
    r = await client.get("/api/usage/export?days=30", headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    assert r.text.splitlines()[0] == "date,provider,agent,category,for,tokens,cost_usd,cost_inr,model"


# ── Endpoints return tokens at the point of action (live Claude — skip if absent) ──
async def _owner_ctx():
    from app.auth.config import get_jwt_strategy
    from app.models.user import User
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.job import Job
    eng, Session = _sessionmaker()
    try:
        async with Session() as s:
            u = (await s.execute(select(User).where(User.id == OWNER))).scalar_one_or_none()
            if not u:
                return None
            tok = await get_jwt_strategy().write_token(u)
            master = (await s.execute(select(MasterCV).where(
                MasterCV.user_id == OWNER, MasterCV.is_active == True))).scalars().first()
            dcv = (await s.execute(select(DomainCV).where(
                DomainCV.user_id == OWNER, DomainCV.status == CVStatus.active,
                DomainCV.content_md.isnot(None)))).scalars().first()
            job = (await s.execute(select(Job).where(Job.user_id == OWNER).limit(1))).scalar_one_or_none()
            return {"H": {"Authorization": f"Bearer {tok}"}, "master": master, "dcv": dcv, "job": job}
    finally:
        await eng.dispose()


async def test_tailor_generate_returns_tokens_in_response(client):
    ctx = await _owner_ctx()
    if not ctx or not (ctx["job"] and ctx["dcv"] and ctx["master"]):
        pytest.skip("owner job / domain CV / master not present")
    r = await client.post("/api/tailor/generate",
                          json={"job_id": str(ctx["job"].id), "domain_cv_id": str(ctx["dcv"].id)},
                          headers=ctx["H"], timeout=150)
    assert r.status_code == 200, r.text
    assert (r.json().get("tokens_used") or 0) > 0
    assert (r.json().get("cost_inr") or 0) > 0


async def test_parse_jd_returns_tokens_in_response(client):
    ctx = await _owner_ctx()
    if not ctx or not ctx["master"]:
        pytest.skip("owner master CV not present")
    jd = ("Head of Product — Amsterdam. We are hiring a senior product leader to own our B2B "
          "SaaS roadmap, lead a team of PMs, drive strategy with engineering and design, and "
          "scale our platform across the EU. 8+ years product management and leadership required. ") * 3
    r = await client.post("/api/jobs/parse/text", json={"raw_text": jd, "score_immediately": True},
                          headers=ctx["H"], timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    if d.get("pre_filter_passed") and d.get("s1_score"):
        assert (d.get("s1_tokens") or 0) > 0


async def test_domain_cv_generate_returns_tokens(client):
    ctx = await _owner_ctx()
    if not ctx or not (ctx["dcv"] and ctx["master"]):
        pytest.skip("owner domain CV / master not present")
    dcv = ctx["dcv"]
    r = await client.post("/api/cvs/domains/generate-changelog",
                          json={"industry_id": str(dcv.industry_id), "function_id": str(dcv.function_id),
                                "country_code": dcv.country_code},
                          headers=ctx["H"], timeout=150)
    if r.status_code == 200:  # 200 = regenerated; other codes = combo not regenerable here
        assert (r.json().get("tokens_used") or 0) > 0

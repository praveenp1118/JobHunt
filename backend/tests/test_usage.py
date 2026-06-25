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

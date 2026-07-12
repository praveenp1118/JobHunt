"""Career Insights tests — serialization, 7-day cache, roadmap score update, community floor, questions."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.models.career import CareerAnalysis, CareerRoadmapItem

ANALYSIS_JSON = {
    "readiness_score": 70.0,
    "scores": {"keywords": 60, "skills": 70, "experience": 75, "certifications": 80, "projects": 65},
    "top_action": {"title": "Add LLM fine-tuning", "impact_pct": 3},
    "keywords": {"missing": [], "present": []},
    "last_cost_inr": 9.06, "last_tokens": 14000,
}


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _uid(client, headers):
    r = await client.get("/api/auth/me", headers=headers)
    return uuid.UUID(r.json()["id"])


async def _seed(uid, *, readiness=70.0, days=7, roadmap_impact=None):
    eng, S = _sm()
    rid = None
    async with S() as s:
        await s.execute(delete(CareerRoadmapItem).where(CareerRoadmapItem.user_id == uid))
        await s.execute(delete(CareerAnalysis).where(CareerAnalysis.user_id == uid))
        aj = dict(ANALYSIS_JSON, readiness_score=readiness)
        s.add(CareerAnalysis(
            user_id=uid, readiness_score=readiness, keywords_score=60, skills_score=70,
            experience_score=75, certifications_score=80, analysis_json=aj, jd_count=5,
            last_analysed_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=days)))
        if roadmap_impact is not None:
            item = CareerRoadmapItem(user_id=uid, category="keyword", title="Add LLM fine-tuning",
                                     impact_pct=roadmap_impact, timeframe="this_week", sort_order=1)
            s.add(item)
            await s.flush()
            rid = item.id
        await s.commit()
    await eng.dispose()
    return rid


async def test_career_analysis_returns_structure(client, user_creds):
    uid = await _uid(client, user_creds["headers"])
    await _seed(uid)
    r = await client.get("/api/career/analysis", headers=user_creds["headers"])
    assert r.status_code == 200
    d = r.json()
    assert d["available"] is True
    assert d["readiness_score"] == 70.0
    assert set(d["scores"]) >= {"keywords", "skills", "experience", "certifications", "projects"}
    assert "roadmap_items" in d and d["last_cost_inr"] == 9.06


async def test_career_analysis_cached_7_days(client, user_creds):
    uid = await _uid(client, user_creds["headers"])
    await _seed(uid, days=7)
    fresh = (await client.get("/api/career/analysis", headers=user_creds["headers"])).json()
    assert fresh["is_fresh"] is True
    await _seed(uid, days=-1)  # expired
    stale = (await client.get("/api/career/analysis", headers=user_creds["headers"])).json()
    assert stale["is_fresh"] is False


async def test_roadmap_item_completion_updates_score(client, user_creds):
    uid = await _uid(client, user_creds["headers"])
    rid = await _seed(uid, readiness=70.0, roadmap_impact=3)
    r = await client.patch(f"/api/career/roadmap/{rid}", json={"is_completed": True},
                           headers=user_creds["headers"])
    assert r.status_code == 200
    assert r.json()["new_readiness_score"] == 73.0
    # un-completing reverts
    r2 = await client.patch(f"/api/career/roadmap/{rid}", json={"is_completed": False},
                            headers=user_creds["headers"])
    assert r2.json()["new_readiness_score"] == 70.0


async def test_community_warming_up_when_no_data(client, user_creds):
    eng, S = _sm()
    async with S() as s:
        await s.execute(text("delete from community_career_insights "
                             "where role_category in ('Senior Product','General','Product')"))
        await s.commit()
    await eng.dispose()
    r = await client.get("/api/career/community", headers=user_creds["headers"])
    assert r.status_code == 200
    d = r.json()
    assert d["warming_up"] is True and d["contributor_count"] < 2


async def test_career_questions_saved(client, user_creds):
    s = await client.post("/api/career/questions",
                          json={"question_key": "manages_team", "answer": "Yes, currently"},
                          headers=user_creds["headers"])
    assert s.status_code == 200 and s.json()["saved"] is True
    g = await client.get("/api/career/questions", headers=user_creds["headers"])
    assert g.json().get("manages_team") == "Yes, currently"


def test_role_category_is_domain_neutral():
    from app.routers.career import _categorize_role
    assert _categorize_role("Head of Product, VP Product") == "Product"
    assert _categorize_role("Finance Director, FP&A Lead") == "Finance"
    assert _categorize_role("VP Operations & Supply Chain") == "Operations"
    assert _categorize_role("") == "General"           # never defaults to product
    assert _categorize_role(None) == "General"

"""
Career Insights router — cached gap analysis (7-day TTL), roadmap, questions, community.
The paid analysis (POST /analyse) is subscription-gated (admins bypass). GET /analysis
never auto-charges — it returns the cache or {available: false} and the frontend triggers.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserCredentials
from app.models.cv import MasterCV
from app.models.job import Job
from app.models.career import CareerAnalysis, CareerRoadmapItem, CareerQuestion, CommunityCareerInsight
from app.auth.dependencies import current_active_user
from app.utils.subscription import require_active_subscription
from app.utils.encryption import decrypt_if_present
from app.utils.model import get_user_model
from app.utils.usage_logger import set_usage_user
from app.agents.career_agent import analyse_career_gaps
from app.config import settings

router = APIRouter()

QUESTION_KEYS = ["manages_pms", "github_public", "b2c_experience", "relocation", "willing_to_do"]


async def _anthropic_key(user, session):
    creds = (await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id))).scalar_one_or_none()
    key = decrypt_if_present(creds.anthropic_api_key_enc) if creds and creds.anthropic_api_key_enc else None
    return key or settings.platform_anthropic_api_key or settings.anthropic_api_key


def _road(r: CareerRoadmapItem) -> dict:
    return {
        "id": str(r.id), "category": r.category, "title": r.title, "description": r.description,
        "impact_pct": r.impact_pct, "timeframe": r.timeframe, "is_completed": r.is_completed,
        "sort_order": r.sort_order,
    }


def _resp(ca: CareerAnalysis, roadmap, is_fresh: bool, usage=None) -> dict:
    out = {
        "available": True,
        "analysis": ca.analysis_json,
        "readiness_score": ca.readiness_score,
        "scores": {
            "keywords": ca.keywords_score, "skills": ca.skills_score,
            "experience": ca.experience_score, "certifications": ca.certifications_score,
            "projects": (ca.analysis_json or {}).get("scores", {}).get("projects"),
        },
        "roadmap_items": [_road(r) for r in roadmap],
        "is_fresh": is_fresh,
        "jd_count": ca.jd_count,
        "last_analysed_at": ca.last_analysed_at.isoformat() if ca.last_analysed_at else None,
        "expires_at": ca.expires_at.isoformat() if ca.expires_at else None,
        "last_cost_inr": (ca.analysis_json or {}).get("last_cost_inr"),
        "last_tokens": (ca.analysis_json or {}).get("last_tokens"),
    }
    if usage:
        out.update(usage)
    return out


async def _run_analysis(user, session) -> dict:
    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
    if not master or not master.content_md:
        raise HTTPException(status_code=400, detail="Upload a master CV first to analyse your career readiness")

    jobs = (await session.execute(
        select(Job).where(Job.user_id == user.id, Job.jd_raw.isnot(None)).limit(50))).scalars().all()
    jd_texts = [(j.jd_md or j.jd_raw) for j in jobs if (j.jd_md or j.jd_raw)]

    answers = {q.question_key: q.answer for q in (await session.execute(
        select(CareerQuestion).where(CareerQuestion.user_id == user.id))).scalars().all()}

    key = await _anthropic_key(user, session)
    model = await get_user_model(user.id, session)
    set_usage_user(user.id)
    analysis = await analyse_career_gaps(master.content_md, jd_texts, answers, key, model,
                                         session=session, user_id=user.id)
    usage = analysis.pop("_usage", {}) or {}
    if not analysis or (analysis.get("readiness_score") is None and not analysis.get("scores")):
        raise HTTPException(status_code=502, detail="Career analysis could not be parsed — please retry")
    scores = analysis.get("scores", {}) or {}

    now = datetime.now(timezone.utc)
    ca = (await session.execute(
        select(CareerAnalysis).where(CareerAnalysis.user_id == user.id))).scalar_one_or_none()
    if not ca:
        ca = CareerAnalysis(user_id=user.id)
        session.add(ca)
    ca.readiness_score = analysis.get("readiness_score")
    ca.keywords_score = scores.get("keywords")
    ca.skills_score = scores.get("skills")
    ca.experience_score = scores.get("experience")
    ca.certifications_score = scores.get("certifications")
    analysis["last_cost_inr"] = usage.get("cost_inr")
    analysis["last_tokens"] = usage.get("tokens_used")
    ca.analysis_json = analysis
    ca.jd_count = len(jd_texts)
    ca.last_analysed_at = now
    ca.expires_at = now + timedelta(days=7)

    await session.execute(delete(CareerRoadmapItem).where(CareerRoadmapItem.user_id == user.id))
    for i, r in enumerate(analysis.get("roadmap", []) or []):
        session.add(CareerRoadmapItem(
            user_id=user.id, category=(r.get("category") or "keyword")[:30], title=(r.get("title") or "")[:255],
            impact_pct=r.get("impact_pct"), timeframe=r.get("timeframe"), sort_order=r.get("sort_order", i)))
    await session.commit()
    await session.refresh(ca)
    roadmap = (await session.execute(
        select(CareerRoadmapItem).where(CareerRoadmapItem.user_id == user.id)
        .order_by(CareerRoadmapItem.sort_order))).scalars().all()
    return _resp(ca, roadmap, True, {"tokens_used": usage.get("tokens_used"), "cost_inr": usage.get("cost_inr")})


@router.get("/analysis")
async def get_analysis(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    ca = (await session.execute(
        select(CareerAnalysis).where(CareerAnalysis.user_id == user.id))).scalar_one_or_none()
    if not ca or not ca.analysis_json:
        return {"available": False, "needs_analysis": True}
    roadmap = (await session.execute(
        select(CareerRoadmapItem).where(CareerRoadmapItem.user_id == user.id)
        .order_by(CareerRoadmapItem.sort_order))).scalars().all()
    fresh = bool(ca.expires_at and ca.expires_at > datetime.now(timezone.utc))
    return _resp(ca, roadmap, fresh)


@router.post("/analyse", dependencies=[Depends(require_active_subscription)])
async def analyse(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    return await _run_analysis(user, session)


class AnswerBody(BaseModel):
    question_key: str
    answer: str


@router.post("/questions")
async def save_answer(body: AnswerBody, user: User = Depends(current_active_user),
                      session: AsyncSession = Depends(get_db)):
    q = (await session.execute(select(CareerQuestion).where(
        CareerQuestion.user_id == user.id, CareerQuestion.question_key == body.question_key))).scalar_one_or_none()
    if not q:
        q = CareerQuestion(user_id=user.id, question_key=body.question_key, answer=body.answer[:500])
        session.add(q)
    else:
        q.answer = body.answer[:500]
        q.answered_at = datetime.now(timezone.utc)
    await session.commit()
    answered = (await session.execute(
        select(CareerQuestion.question_key).where(CareerQuestion.user_id == user.id))).scalars().all()
    return {"saved": True, "all_answered": set(QUESTION_KEYS).issubset(set(answered))}


@router.get("/questions")
async def get_answers(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(
        select(CareerQuestion).where(CareerQuestion.user_id == user.id))).scalars().all()
    return {q.question_key: q.answer for q in rows}


class RoadmapBody(BaseModel):
    is_completed: bool


@router.patch("/roadmap/{item_id}")
async def update_roadmap(item_id: uuid.UUID, body: RoadmapBody,
                         user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    item = (await session.execute(select(CareerRoadmapItem).where(
        CareerRoadmapItem.id == item_id, CareerRoadmapItem.user_id == user.id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Roadmap item not found")
    was = item.is_completed
    item.is_completed = body.is_completed
    item.completed_at = datetime.now(timezone.utc) if body.is_completed else None

    # Reflect completion in the readiness score (+impact when newly completing, − when un-completing).
    ca = (await session.execute(
        select(CareerAnalysis).where(CareerAnalysis.user_id == user.id))).scalar_one_or_none()
    new_score = ca.readiness_score if ca else None
    if ca and ca.readiness_score is not None and (item.impact_pct or 0) and was != body.is_completed:
        delta = (item.impact_pct or 0) * (1 if body.is_completed else -1)
        new_score = max(0, min(100, round(ca.readiness_score + delta, 1)))
        ca.readiness_score = new_score
    await session.commit()
    return {"updated": True, "new_readiness_score": new_score}


@router.get("/community")
async def community(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    # Role category from the user's analysis (best effort); blank-safe.
    ca = (await session.execute(
        select(CareerAnalysis).where(CareerAnalysis.user_id == user.id))).scalar_one_or_none()
    role_category = ((ca.analysis_json or {}).get("role_category") if ca else None) or "Senior Product"
    rows = (await session.execute(
        select(CommunityCareerInsight).where(CommunityCareerInsight.role_category == role_category)
        .order_by(CommunityCareerInsight.frequency_pct.desc().nullslast()))).scalars().all()
    contributors = max((r.contributor_count for r in rows), default=0)
    if contributors < 2:
        return {"warming_up": True, "contributor_count": contributors, "role_category": role_category}
    return {
        "warming_up": False, "role_category": role_category, "contributor_count": contributors,
        "insights": [{"type": r.insight_type, "value": r.insight_value, "frequency_pct": r.frequency_pct,
                      "success_stories": r.success_stories} for r in rows[:10]],
    }


@router.post("/share")
async def share(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    ca = (await session.execute(
        select(CareerAnalysis).where(CareerAnalysis.user_id == user.id))).scalar_one_or_none()
    if not ca or not ca.analysis_json:
        raise HTTPException(status_code=400, detail="Run an analysis first")
    role_category = ca.analysis_json.get("role_category") or "Senior Product"
    missing = (ca.analysis_json.get("keywords", {}) or {}).get("missing", []) or []
    shared = 0
    for kw in missing[:20]:
        val = (kw.get("keyword") or "")[:255]
        if not val:
            continue
        existing = (await session.execute(select(CommunityCareerInsight).where(
            CommunityCareerInsight.role_category == role_category,
            CommunityCareerInsight.insight_type == "keyword",
            CommunityCareerInsight.insight_value == val))).scalar_one_or_none()
        if existing:
            existing.contributor_count += 1
            existing.frequency_pct = kw.get("frequency_pct") or existing.frequency_pct
        else:
            session.add(CommunityCareerInsight(
                role_category=role_category, insight_type="keyword", insight_value=val,
                frequency_pct=kw.get("frequency_pct"), contributor_count=1, success_stories=0))
        shared += 1
    await session.commit()
    return {"shared": True, "patterns_shared": shared}

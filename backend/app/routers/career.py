"""
Career Insights router — cached gap analysis (7-day TTL), roadmap, questions, community.
The paid analysis (POST /analyse) is subscription-gated (admins bypass). GET /analysis
never auto-charges — it returns the cache or {available: false} and the frontend triggers.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Query
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


SOURCE_LABELS = {"rss": "RSS feeds", "apify": "LinkedIn / Apify", "gmail_alert": "Gmail Alerts", "manual": "Manual"}
MARKET_LABELS = {"NL": "Netherlands", "EU": "EU", "Dubai": "Dubai", "SG": "Singapore", "IN": "India"}


async def _domain_label(session, dcv_id) -> str:
    from app.models.cv import DomainCV
    from app.models.domain import IndustryVertical
    row = (await session.execute(
        select(IndustryVertical.label, DomainCV.country_code).select_from(DomainCV)
        .outerjoin(IndustryVertical, IndustryVertical.id == DomainCV.industry_id)
        .where(DomainCV.id == dcv_id))).first()
    return f"{row[0] or 'Domain'} × {row[1] or '—'}" if row else "Domain CV"


async def _resolve_filter(session, source, feed_id, domain_cv_id, market):
    """Return (job_clauses, filter_hash, filter_label, fields). Only one filter is active
    at a time (matches the single-select dropdown)."""
    from app.models.job import JobSource
    fields = {"filter_source": None, "filter_feed_id": None, "filter_domain_cv_id": None, "filter_market": None}
    if source:
        try:
            js = JobSource(source)
            fields["filter_source"] = source
            return [Job.source == js], f"source:{source}", SOURCE_LABELS.get(source, source), fields
        except ValueError:
            pass
    if feed_id:
        try:
            fid = uuid.UUID(feed_id)
            from app.models.domain import UserFeed
            f = (await session.execute(select(UserFeed).where(UserFeed.id == fid))).scalar_one_or_none()
            fields["filter_feed_id"] = fid
            return [Job.source_feed_id == fid], f"feed:{feed_id}", (f.name if f else "Feed"), fields
        except (ValueError, TypeError):
            pass
    if domain_cv_id:
        try:
            did = uuid.UUID(domain_cv_id)
            fields["filter_domain_cv_id"] = did
            return [Job.best_domain_cv_id == did], f"domain:{domain_cv_id}", await _domain_label(session, did), fields
        except (ValueError, TypeError):
            pass
    if market:
        fields["filter_market"] = market
        return [Job.market == market], f"market:{market}", f"{MARKET_LABELS.get(market, market)} market", fields
    return [], "all", "All jobs", fields


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
        "filter_hash": ca.filter_hash,
        "filter_label": ca.filter_label,
    }
    if usage:
        out.update(usage)
    return out


async def _run_analysis(user, session, source=None, feed_id=None, domain_cv_id=None, market=None) -> dict:
    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
    if not master or not master.content_md:
        raise HTTPException(status_code=400, detail="Upload a master CV first to analyse your career readiness")

    clauses, filter_hash, filter_label, fields = await _resolve_filter(session, source, feed_id, domain_cv_id, market)
    # Best-fit JDs first (highest S1d), analyse up to 100.
    from sqlalchemy import func as _func
    jobs = (await session.execute(
        select(Job).where(Job.user_id == user.id, Job.jd_raw.isnot(None), *clauses)
        .order_by(_func.coalesce(Job.s1d, Job.s1).desc().nullslast()).limit(100))).scalars().all()
    jd_texts = [(j.jd_md or j.jd_raw) for j in jobs if (j.jd_md or j.jd_raw)]
    if not jd_texts:
        raise HTTPException(status_code=400, detail=f"No jobs match this filter ({filter_label}) — try a broader filter")

    answers = {q.question_key: q.answer for q in (await session.execute(
        select(CareerQuestion).where(CareerQuestion.user_id == user.id))).scalars().all()}

    key = await _anthropic_key(user, session)
    # Prefer the user's configured career_model (Settings → Scoring); fall back to their default.
    from app.models.user import UserPreferences
    _prefs = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id))).scalars().first()
    model = (getattr(_prefs, "career_model", None)) or await get_user_model(user.id, session)
    set_usage_user(user.id)
    analysis = await analyse_career_gaps(master.content_md, jd_texts, answers, key, model,
                                         session=session, user_id=user.id,
                                         master_essence=master.essence_json)
    usage = analysis.pop("_usage", {}) or {}
    if not analysis or (analysis.get("readiness_score") is None and not analysis.get("scores")):
        raise HTTPException(status_code=502, detail="Career analysis could not be parsed — please retry")
    scores = analysis.get("scores", {}) or {}

    now = datetime.now(timezone.utc)
    ca = (await session.execute(select(CareerAnalysis).where(
        CareerAnalysis.user_id == user.id, CareerAnalysis.filter_hash == filter_hash))).scalar_one_or_none()
    if not ca:
        ca = CareerAnalysis(user_id=user.id, filter_hash=filter_hash)
        session.add(ca)
    ca.filter_label = filter_label
    ca.filter_source = fields["filter_source"]
    ca.filter_feed_id = fields["filter_feed_id"]
    ca.filter_domain_cv_id = fields["filter_domain_cv_id"]
    ca.filter_market = fields["filter_market"]
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

    await session.execute(delete(CareerRoadmapItem).where(
        CareerRoadmapItem.user_id == user.id, CareerRoadmapItem.filter_hash == filter_hash))
    for i, r in enumerate(analysis.get("roadmap", []) or []):
        session.add(CareerRoadmapItem(
            user_id=user.id, filter_hash=filter_hash,
            category=(r.get("category") or "keyword")[:30], title=(r.get("title") or "")[:255],
            impact_pct=r.get("impact_pct"), timeframe=r.get("timeframe"), sort_order=r.get("sort_order", i)))
    await session.commit()
    await session.refresh(ca)
    roadmap = (await session.execute(
        select(CareerRoadmapItem).where(
            CareerRoadmapItem.user_id == user.id, CareerRoadmapItem.filter_hash == filter_hash)
        .order_by(CareerRoadmapItem.sort_order))).scalars().all()
    return _resp(ca, roadmap, True, {"tokens_used": usage.get("tokens_used"), "cost_inr": usage.get("cost_inr")})


# ── Real readiness from aggregated ATS + Pursuit scores (no Claude call) ──────
_ATS_MAX = {"keyword_density": 30, "required_skills": 25, "experience_years": 20, "seniority_alignment": 15, "education": 10}
_ATS_LABEL = {"keyword_density": "Keywords", "required_skills": "Required skills", "experience_years": "Experience", "seniority_alignment": "Seniority", "education": "Education"}
_PUR_MAX = {"human_excitement": 40, "career_move_quality": 25, "achievability": 20, "effort_reward": 15}
_PUR_LABEL = {"human_excitement": "Human appeal", "career_move_quality": "Career fit", "achievability": "Achievability", "effort_reward": "Timing"}


def _agg_components(jobs, metric, maxes, labels):
    """Average each component score across jobs, normalised to 0-100, + the weakest (top gap)."""
    sums = {k: 0.0 for k in maxes}
    cnts = {k: 0 for k in maxes}
    for j in jobs:
        comps = (((j.score_components or {}).get("master") or {}).get(metric) or {}).get("components") or {}
        for k in maxes:
            v = (comps.get(k) or {}).get("score")
            if isinstance(v, (int, float)):
                sums[k] += float(v)
                cnts[k] += 1
    out = {}
    for k in maxes:
        out[k] = {"score": (round((sums[k] / cnts[k]) / maxes[k] * 100) if cnts[k] else None),
                  "label": labels[k], "max": 100}
    valid = {k: v["score"] for k, v in out.items() if v["score"] is not None}
    top_gap = min(valid, key=valid.get) if valid else None
    return out, top_gap


@router.get("/readiness-scores")
async def readiness_scores(
    source: Optional[str] = Query(None), feed_id: Optional[str] = Query(None),
    domain_cv_id: Optional[str] = Query(None), market: Optional[str] = Query(None),
    user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db),
):
    """Instant, free readiness from real aggregated ATS + Pursuit scores (no Claude call).
    Honours the same filter params as the rest of Career Insights."""
    clauses, _h, filter_label, _f = await _resolve_filter(session, source, feed_id, domain_cv_id, market)
    jobs = (await session.execute(select(Job).where(
        Job.user_id == user.id, Job.ats_master.isnot(None), Job.pursuit_master.isnot(None),
        Job.score_components.isnot(None), *clauses))).scalars().all()
    if not jobs:
        return {"no_data": True, "jobs_scored": 0, "filter_label": filter_label}

    ats_comps, ats_gap = _agg_components(jobs, "ats", _ATS_MAX, _ATS_LABEL)
    pur_comps, pur_gap = _agg_components(jobs, "pursuit", _PUR_MAX, _PUR_LABEL)
    n = len(jobs)
    avg_ats = round(sum(j.ats_master for j in jobs) / n)
    avg_pur = round(sum(j.pursuit_master for j in jobs) / n)
    return {
        "ats": {"overall": avg_ats, "components": ats_comps, "top_gap": ats_gap,
                "top_gap_label": _ATS_LABEL.get(ats_gap), "jobs_scored": n},
        "pursuit": {"overall": avg_pur, "components": pur_comps, "top_gap": pur_gap,
                    "top_gap_label": _PUR_LABEL.get(pur_gap), "jobs_scored": n},
        "overall": round(avg_ats * 0.4 + avg_pur * 0.6),
        "avg_ats": avg_ats, "avg_pursuit": avg_pur,
        "filter_label": filter_label, "jobs_scored": n,
    }


@router.get("/analysis")
async def get_analysis(
    source: Optional[str] = Query(None), feed_id: Optional[str] = Query(None),
    domain_cv_id: Optional[str] = Query(None), market: Optional[str] = Query(None),
    user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db),
):
    _clauses, filter_hash, filter_label, _f = await _resolve_filter(session, source, feed_id, domain_cv_id, market)
    ca = (await session.execute(select(CareerAnalysis).where(
        CareerAnalysis.user_id == user.id, CareerAnalysis.filter_hash == filter_hash))).scalar_one_or_none()
    if not ca or not ca.analysis_json:
        return {"available": False, "needs_analysis": True, "filter_hash": filter_hash, "filter_label": filter_label}
    roadmap = (await session.execute(
        select(CareerRoadmapItem).where(
            CareerRoadmapItem.user_id == user.id, CareerRoadmapItem.filter_hash == filter_hash)
        .order_by(CareerRoadmapItem.sort_order))).scalars().all()
    fresh = bool(ca.expires_at and ca.expires_at > datetime.now(timezone.utc))
    return _resp(ca, roadmap, fresh)


@router.post("/analyse", dependencies=[Depends(require_active_subscription)])
async def analyse(
    response: Response,
    source: Optional[str] = Query(None), feed_id: Optional[str] = Query(None),
    domain_cv_id: Optional[str] = Query(None), market: Optional[str] = Query(None),
    user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db),
):
    from app.utils.rate_limiter import enforce_rate_limit
    _rl = await enforce_rate_limit(user.id, "career_analyse", session)
    response.headers["X-RateLimit-Remaining"] = str(_rl["remaining"])
    return await _run_analysis(user, session, source, feed_id, domain_cv_id, market)


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

    # Reflect completion in the readiness score of the analysis this item belongs to.
    ca = (await session.execute(select(CareerAnalysis).where(
        CareerAnalysis.user_id == user.id, CareerAnalysis.filter_hash == item.filter_hash))).scalar_one_or_none()
    new_score = ca.readiness_score if ca else None
    if ca and ca.readiness_score is not None and (item.impact_pct or 0) and was != body.is_completed:
        delta = (item.impact_pct or 0) * (1 if body.is_completed else -1)
        new_score = max(0, min(100, round(ca.readiness_score + delta, 1)))
        ca.readiness_score = new_score
    await session.commit()
    return {"updated": True, "new_readiness_score": new_score}


@router.get("/community")
async def community(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    # Role category from the user's "all jobs" analysis (best effort); blank-safe.
    ca = (await session.execute(select(CareerAnalysis).where(
        CareerAnalysis.user_id == user.id, CareerAnalysis.filter_hash == "all"))).scalar_one_or_none()
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
    ca = (await session.execute(select(CareerAnalysis).where(
        CareerAnalysis.user_id == user.id, CareerAnalysis.filter_hash == "all"))).scalar_one_or_none()
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

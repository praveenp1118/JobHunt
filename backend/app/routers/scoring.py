"""Hybrid-RAG scoring config + live cost estimate (Settings → Scoring & Cost)."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserPreferences
from app.auth.dependencies import current_active_user
from app.agents.rag_scorer import SCORING_PRESETS, CONFIG_FIELDS, config_from_prefs, estimate_scan_cost

router = APIRouter()

AVG_JOBS_PER_FEED = 25
# Indicative per-job ₹ cost per model (for the dropdown labels in the UI).
MODEL_COSTS = {
    "claude-haiku-4-5": {"essence": 0.03, "full": 0.06, "domain": 0.03},
    "claude-sonnet-4-6": {"essence": 0.58, "full": 0.58, "domain": 0.58},
    "claude-opus-4-6": {"essence": 2.90, "full": 2.90, "domain": 2.90},
}


async def _get_prefs(session, user_id) -> UserPreferences:
    p = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id))).scalars().first()
    if not p:
        p = UserPreferences(user_id=user_id)
        session.add(p)
        await session.commit()
        await session.refresh(p)
    return p


def _serialize(prefs) -> dict:
    return {
        "scoring_preset": prefs.scoring_preset,
        "keyword_match_threshold": prefs.keyword_match_threshold,
        "s1_essence_model": prefs.s1_essence_model,
        "s1_essence_reject_below": prefs.s1_essence_reject_below,
        "s1_full_model": prefs.s1_full_model,
        "s1_borderline_low": prefs.s1_borderline_low,
        "s1_borderline_high": prefs.s1_borderline_high,
        "domain_score_model": prefs.domain_score_model,
        "domain_score_min_s1": prefs.domain_score_min_s1,
        "career_model": prefs.career_model,
        "scoring_batch_size": prefs.scoring_batch_size,
    }


@router.get("/config")
async def get_scoring_config(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    prefs = await _get_prefs(session, user.id)
    return {**_serialize(prefs), "presets": SCORING_PRESETS, "model_costs": MODEL_COSTS}


class ScoringUpdate(BaseModel):
    scoring_preset: Optional[str] = None
    keyword_match_threshold: Optional[int] = None
    s1_essence_model: Optional[str] = None
    s1_essence_reject_below: Optional[int] = None
    s1_full_model: Optional[str] = None
    s1_borderline_low: Optional[int] = None
    s1_borderline_high: Optional[int] = None
    domain_score_model: Optional[str] = None
    domain_score_min_s1: Optional[int] = None
    career_model: Optional[str] = None
    scoring_batch_size: Optional[int] = None


@router.patch("/config")
async def update_scoring_config(body: ScoringUpdate, user: User = Depends(current_active_user),
                                session: AsyncSession = Depends(get_db)):
    prefs = await _get_prefs(session, user.id)
    data = body.model_dump(exclude_unset=True)
    # A preset change auto-fills all stage fields (the UI then lets the user fine-tune).
    if "scoring_preset" in data and data["scoring_preset"] in SCORING_PRESETS:
        prefs.scoring_preset = data["scoring_preset"]
        for k, v in SCORING_PRESETS[data["scoring_preset"]].items():
            setattr(prefs, k, v)
    # Explicit field overrides win.
    for k, v in data.items():
        if k == "scoring_preset":
            continue
        setattr(prefs, k, v)
        if k in CONFIG_FIELDS and "scoring_preset" not in data:
            prefs.scoring_preset = "custom"  # user fine-tuned → no longer a named preset
    await session.commit()
    await session.refresh(prefs)
    return _serialize(prefs)


@router.get("/estimate")
async def scoring_estimate(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    from app.models.domain import UserFeed
    from app.models.cv import DomainCV, CVStatus
    prefs = await _get_prefs(session, user.id)
    config = config_from_prefs(prefs)

    active_feeds = (await session.execute(
        select(func.count(UserFeed.id)).where(UserFeed.user_id == user.id, UserFeed.is_active == True))).scalar() or 0
    num_domains = (await session.execute(
        select(func.count(DomainCV.id)).where(DomainCV.user_id == user.id, DomainCV.status == CVStatus.active))).scalar() or 0

    total_jobs = active_feeds * AVG_JOBS_PER_FEED
    est = estimate_scan_cost(config, total_jobs, num_domains)
    return {
        "active_feeds": active_feeds,
        "avg_jobs_per_feed": AVG_JOBS_PER_FEED,
        "num_domain_cvs": num_domains,
        "monthly_cost_inr": round(est["estimated_cost_inr"] * 4, 2),
        **est,
    }

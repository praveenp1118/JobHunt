"""
Community Insights router — anonymised, aggregated job-search data.
Insights surface only with >= 2 contributors (privacy). NO CV content / PII.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserPreferences
from app.models.job import Job
from app.models.cv import TailoredCV, ChangeLog
from app.models.community import CommunityJobInsight, CommunityContribution
from app.auth.dependencies import current_active_user
from app.utils.community import get_community_insights, upsert_community_insights

router = APIRouter()


@router.get("/insights")
async def insights(
    company: str,
    role: str,
    market: Optional[str] = None,
    jd_hash: Optional[str] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    data = await get_community_insights(session, company, role, market, jd_hash)
    if not data:
        return {"available": False}
    data["tokens_saved"] = True  # community data → 0 tokens spent by the recipient
    return data


@router.post("/share/{job_id}")
async def share_job(
    job_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Manually contribute a job's insights (works regardless of the auto-share toggle)."""
    job = (await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tcv = None
    changelog = []
    if job.tailored_cv_id:
        tcv = (await session.execute(
            select(TailoredCV).where(TailoredCV.id == job.tailored_cv_id))).scalar_one_or_none()
        changelog = list((await session.execute(
            select(ChangeLog).where(ChangeLog.tailored_cv_id == job.tailored_cv_id))).scalars().all())

    insight_id = await upsert_community_insights(session, user.id, job, tcv, changelog)
    await session.commit()
    if not insight_id:
        raise HTTPException(status_code=400, detail="Nothing to share — job needs a company, role, and scoring/tailoring")
    return {"shared": True, "insight_id": str(insight_id)}


@router.get("/my-contributions")
async def my_contributions(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    rows = (await session.execute(
        select(CommunityContribution, Job.company, Job.role, CommunityJobInsight.contributor_count)
        .join(Job, Job.id == CommunityContribution.job_id)
        .join(CommunityJobInsight, CommunityJobInsight.id == CommunityContribution.insight_id)
        .where(CommunityContribution.user_id == user.id)
        .order_by(CommunityContribution.created_at.desc())
    )).all()
    return [
        {
            "job_id": str(c.job_id),
            "insight_id": str(c.insight_id),
            "company": company,
            "role": role,
            "contributor_count": cc,
            "contributed_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c, company, role, cc in rows
    ]


class CommunityPrefs(BaseModel):
    community_sharing_enabled: bool


@router.patch("/preferences")
async def update_preferences(
    body: CommunityPrefs,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    prefs = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id))).scalar_one_or_none()
    if not prefs:
        prefs = UserPreferences(user_id=user.id, community_sharing_enabled=body.community_sharing_enabled)
        session.add(prefs)
    else:
        prefs.community_sharing_enabled = body.community_sharing_enabled
    await session.commit()
    return {"community_sharing_enabled": body.community_sharing_enabled}

"""
API usage router — token + cost visibility for the Settings → API Usage tab.
Read-only over api_usage_logs (written by usage_logger).
"""
import csv
import io
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.usage import APIUsageLog
from app.auth.dependencies import current_active_user

router = APIRouter()


def _serialize(r: APIUsageLog) -> dict:
    return {
        "id": str(r.id),
        "provider": r.provider,
        "agent_name": r.agent_name,
        "category": r.category,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "entity_label": r.entity_label,
        "model": r.model,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "total_tokens": r.total_tokens,
        "estimated_cost_usd": r.estimated_cost_usd,
        "estimated_cost_inr": r.estimated_cost_inr,
        "actor_id": r.actor_id,
        "runs_requested": r.runs_requested,
        "runs_returned": r.runs_returned,
        "jobs_saved": r.jobs_saved,
        "result_summary": r.result_summary,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/logs")
async def get_usage_logs(
    provider: str = "all",
    category: str = "all",
    days: int = 30,
    limit: int = 100,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [APIUsageLog.user_id == user.id, APIUsageLog.created_at >= since]
    if provider and provider != "all":
        filters.append(APIUsageLog.provider == provider)
    if category and category != "all":
        filters.append(APIUsageLog.category == category)

    rows = (await session.execute(
        select(APIUsageLog).where(*filters)
        .order_by(APIUsageLog.created_at.desc()).limit(limit)
    )).scalars().all()

    # Summary covers the whole window (independent of the provider/category/limit filters).
    all_rows = (await session.execute(
        select(APIUsageLog).where(
            APIUsageLog.user_id == user.id, APIUsageLog.created_at >= since)
    )).scalars().all()

    anth = {"total_tokens": 0, "total_cost_usd": 0.0, "total_cost_inr": 0.0,
            "call_count": 0, "by_category": {}, "by_model": {}}
    apify = {"total_runs": 0, "total_cost_usd": 0.0, "total_cost_inr": 0.0, "actor_count": 0}
    # Bright Data kept SEPARATE from Apify — credit usage shown on its own (cost is null:
    # the API returns none, so the dashboard meter is the source of truth).
    brightdata = {"total_runs": 0, "jobs_saved": 0, "sub_source_count": 0, "cost_available": False}
    actors = set()
    bd_subs = set()

    def _tier(model: str) -> str:
        m = (model or "").lower()
        return ("Haiku" if "haiku" in m else "Sonnet" if "sonnet" in m
                else "Opus" if "opus" in m else (model or "other"))

    for r in all_rows:
        if r.provider == "anthropic":
            anth["total_tokens"] += r.total_tokens or 0
            anth["total_cost_usd"] += r.estimated_cost_usd or 0.0
            anth["total_cost_inr"] += r.estimated_cost_inr or 0.0
            anth["call_count"] += 1
            c = anth["by_category"].setdefault(r.category, {"tokens": 0, "cost": 0.0, "count": 0})
            c["tokens"] += r.total_tokens or 0
            c["cost"] += r.estimated_cost_inr or 0.0
            c["count"] += 1
            # Tiered-model summary (Haiku vs Sonnet vs Opus) — shows the optimization in ₹.
            mt = anth["by_model"].setdefault(_tier(r.model), {"count": 0, "cost": 0.0, "tokens": 0})
            mt["count"] += 1
            mt["cost"] += r.estimated_cost_inr or 0.0
            mt["tokens"] += r.total_tokens or 0
        elif r.provider == "apify":
            apify["total_runs"] += r.runs_returned or 0
            apify["total_cost_usd"] += r.estimated_cost_usd or 0.0
            apify["total_cost_inr"] += r.estimated_cost_inr or 0.0
            if r.actor_id:
                actors.add(r.actor_id)
        elif r.provider == "brightdata":
            brightdata["total_runs"] += r.runs_returned or 0
            brightdata["jobs_saved"] += r.jobs_saved or 0
            if r.actor_id:
                bd_subs.add(r.actor_id)
    apify["actor_count"] = len(actors)
    brightdata["sub_source_count"] = len(bd_subs)
    anth["total_cost_usd"] = round(anth["total_cost_usd"], 4)
    anth["total_cost_inr"] = round(anth["total_cost_inr"], 2)
    apify["total_cost_usd"] = round(apify["total_cost_usd"], 4)
    apify["total_cost_inr"] = round(apify["total_cost_inr"], 2)
    for c in anth["by_category"].values():
        c["cost"] = round(c["cost"], 2)
    for m in anth["by_model"].values():
        m["cost"] = round(m["cost"], 2)

    return {"logs": [_serialize(r) for r in rows],
            "summary": {"anthropic": anth, "apify": apify, "brightdata": brightdata}}


@router.get("/export")
async def export_usage_csv(
    days: int = 30,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(APIUsageLog).where(
            APIUsageLog.user_id == user.id, APIUsageLog.created_at >= since)
        .order_by(APIUsageLog.created_at.desc())
    )).scalars().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "provider", "agent", "category", "for", "tokens", "cost_usd", "cost_inr", "model"])
    for r in rows:
        w.writerow([
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            r.provider, r.agent_name, r.category, r.entity_label or "",
            r.total_tokens if r.total_tokens is not None else "",
            r.estimated_cost_usd if r.estimated_cost_usd is not None else "",
            r.estimated_cost_inr if r.estimated_cost_inr is not None else "",
            r.model or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=jobhunt_usage_{days}d.csv"},
    )

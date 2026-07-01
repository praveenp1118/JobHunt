"""
Feeds router — manage RSS and Apify feeds, trigger manual scans.
"""
import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.domain import UserFeed, UserTargetCompany
from app.models.admin import RunLog, RunType, RunStatus
from app.auth.dependencies import current_active_user
from app.utils.subscription import require_active_subscription
from app.schemas.feed import (
    FeedRead, FeedCreate, FeedUpdate,
    ScanResult, TargetCompanyRead, TargetCompanyCreate,
    FeedSuggestRequest, FeedSuggestion, ApifyStoreActor,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════
# V2: Apify Store actor search (dynamic dropdown in Add feed modal)
# ══════════════════════════════════════════════════════════════

@router.get("/feeds/apify-actors", response_model=List[ApifyStoreActor])
async def search_apify_actors(
    search: str = "jobs scraper",
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Search the Apify Store for actors matching `search`, using the user's
    Apify token. Returns actors sorted by popularity (totalRuns) desc."""
    import httpx
    from app.models.user import UserCredentials
    from app.utils.encryption import decrypt_if_present
    from app.config import settings

    # Resolve Apify token: user's own first, then platform fallback
    creds = (await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )).scalar_one_or_none()
    token = None
    if creds and creds.apify_token_enc:
        token = decrypt_if_present(creds.apify_token_enc)
    token = token or settings.platform_apify_token or settings.apify_token
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Add your Apify token in Settings → Plan & Keys first",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.get(
                "https://api.apify.com/v2/store",
                params={"search": search, "limit": 10},
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Apify store search failed: {e}")

    items = (resp.json().get("data") or {}).get("items") or []
    actors = [
        ApifyStoreActor(
            id=it.get("id") or "",
            name=it.get("title") or it.get("name") or "Untitled actor",
            description=it.get("description") or "",
            runs=int((it.get("stats") or {}).get("totalRuns") or 0),
        )
        for it in items
        if it.get("id")
    ]
    actors.sort(key=lambda a: a.runs, reverse=True)
    return actors


# ══════════════════════════════════════════════════════════════
# V2: domain-CV-driven feed suggestion (powers the Add feed modal)
# ══════════════════════════════════════════════════════════════

@router.post("/feeds/suggest", response_model=FeedSuggestion,
             dependencies=[Depends(require_active_subscription)])
async def suggest_feed(
    body: FeedSuggestRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Given a domain CV, use Claude to generate search keywords and return the
    matching RSS board URLs + known Apify actors to pre-fill the Add feed modal."""
    from app.models.cv import DomainCV
    from app.models.domain import IndustryVertical, FunctionalDiscipline
    from app.agents.feed_agents import (
        generate_feed_keywords, get_rss_board_options, KNOWN_APIFY_ACTORS,
    )
    from app.routers.cvs import _get_anthropic_key
    from app.config import settings

    cv = (await session.execute(
        select(DomainCV).where(DomainCV.id == body.domain_cv_id, DomainCV.user_id == user.id)
    )).scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="Domain CV not found")

    # Resolve industry/function labels + industry code
    industry_label, function_label, industry_code = "Product", "Product Management", "GN"
    if cv.industry_id:
        ind = (await session.execute(
            select(IndustryVertical).where(IndustryVertical.id == cv.industry_id)
        )).scalar_one_or_none()
        if ind:
            industry_label, industry_code = ind.label, ind.code
    if cv.function_id:
        fn = (await session.execute(
            select(FunctionalDiscipline).where(FunctionalDiscipline.id == cv.function_id)
        )).scalar_one_or_none()
        if fn:
            function_label = fn.label

    country_code = cv.country_code or "NL"

    # Generate keywords with Claude (graceful fallback so the modal never blocks)
    from app.utils.usage_logger import set_usage_user
    set_usage_user(user.id)
    api_key = await _get_anthropic_key(user, session)
    search_keywords = f"head of product {industry_label.lower()}"
    feed_name = f"{industry_label} × {function_label}"
    if cv.content_md and api_key:
        try:
            result = await generate_feed_keywords(
                domain_cv_content=cv.content_md,
                industry_label=industry_label,
                function_label=function_label,
                country_code=country_code,
                api_key=api_key,
                essence=cv.essence_json,
            )
            search_keywords = result.get("search_keywords") or search_keywords
            feed_name = result.get("feed_name") or feed_name
        except Exception as e:
            print(f"⚠️ Feed keyword generation failed, using defaults: {e}")

    from app.utils.usage_logger import get_session_usage
    _u = get_session_usage()
    return FeedSuggestion(
        domain_cv_id=cv.id,
        feed_name=feed_name,
        search_keywords=search_keywords,
        rss_boards=get_rss_board_options(industry_code, country_code, search_keywords),
        apify_actors=KNOWN_APIFY_ACTORS,
        tokens_used=_u["tokens"] or None,
        cost_inr=round(_u["cost_inr"], 2) or None,
    )


# ══════════════════════════════════════════════════════════════
# FEEDS
# ══════════════════════════════════════════════════════════════

@router.get("/feeds", response_model=List[FeedRead])
async def list_feeds(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """List all feeds (platform + user's own)."""
    result = await session.execute(
        select(UserFeed)
        .where(UserFeed.user_id == user.id)
        .order_by(UserFeed.is_platform.desc(), UserFeed.created_at)
    )
    return [FeedRead.model_validate(f) for f in result.scalars().all()]


@router.get("/feeds/with-counts")
async def feeds_with_counts(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Active feeds + the count of jobs each has surfaced (for the Dashboard filter)."""
    from sqlalchemy import func
    from app.models.job import Job
    feeds = (await session.execute(
        select(UserFeed).where(UserFeed.user_id == user.id, UserFeed.is_active == True)
        .order_by(UserFeed.name))).scalars().all()
    rows = (await session.execute(
        select(Job.source_feed_id, func.count(Job.id))
        .where(Job.user_id == user.id, Job.source_feed_id != None)
        .group_by(Job.source_feed_id))).all()
    cmap = {str(r[0]): r[1] for r in rows}
    return [{"feed_id": str(f.id), "name": f.name, "feed_type": f.feed_type,
             "job_count": cmap.get(str(f.id), 0)} for f in feeds]


@router.get("/feeds/performance")
async def feeds_performance(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Per-feed performance — job count, avg fit, applied, and a composite quality score.
    Includes a synthetic 'Gmail Alerts' row for alert-sourced jobs (no UserFeed)."""
    from sqlalchemy import func
    from app.models.job import Job, JobStatus, JobSource
    from app.models.user import UserPreferences

    prefs = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id))).scalar_one_or_none()
    thr = prefs.s1_min_threshold if prefs and prefs.s1_min_threshold else 65

    feeds = (await session.execute(
        select(UserFeed).where(UserFeed.user_id == user.id))).scalars().all()
    feed_map = {str(f.id): f for f in feeds}

    rows = (await session.execute(
        select(
            Job.source_feed_id,
            func.count(Job.id),
            func.avg(Job.s1d),
            func.avg(Job.s1),
            func.count(Job.id).filter(Job.status == JobStatus.applied),
            func.count(Job.id).filter(func.coalesce(Job.s1d, Job.s1) >= thr),
            func.avg(Job.ats_master),
            func.avg(Job.pursuit_master),
        ).where(Job.user_id == user.id, Job.source_feed_id != None)
        .group_by(Job.source_feed_id))).all()

    def _quality(avg_s1d, applied, count):
        if avg_s1d is None or not count:
            return None
        return round((avg_s1d / 100) * 0.6 + (applied / count) * 0.4, 3)

    def _r(v):
        return round(v, 1) if v is not None else None

    out = []
    for fid, count, avg_s1d, avg_s1, applied, above, avg_ats, avg_pur in rows:
        f = feed_map.get(str(fid))
        if not f:
            continue
        a1d = round(avg_s1d, 1) if avg_s1d is not None else None
        out.append({
            "feed_id": str(fid), "feed_name": f.name, "feed_type": f.feed_type,
            "job_count": count, "avg_s1d": a1d,
            "avg_s1": round(avg_s1, 1) if avg_s1 is not None else None,
            "avg_ats_master": _r(avg_ats), "avg_pursuit_master": _r(avg_pur),
            "applied_count": applied, "above_threshold_count": above,
            "quality_score": _quality(a1d, applied, count),
        })

    # Synthetic Gmail Alerts row (alert-sourced jobs have no source_feed_id).
    g = (await session.execute(
        select(
            func.count(Job.id), func.avg(Job.s1d), func.avg(Job.s1),
            func.count(Job.id).filter(Job.status == JobStatus.applied),
            func.count(Job.id).filter(func.coalesce(Job.s1d, Job.s1) >= thr),
            func.avg(Job.ats_master), func.avg(Job.pursuit_master),
        ).where(Job.user_id == user.id, Job.source == JobSource.gmail_alert))).first()
    if g and g[0]:
        a1d = round(g[1], 1) if g[1] is not None else None
        out.append({
            "feed_id": None, "feed_name": "Gmail Alerts", "feed_type": "gmail_alert",
            "job_count": g[0], "avg_s1d": a1d,
            "avg_s1": round(g[2], 1) if g[2] is not None else None,
            "avg_ats_master": _r(g[5]), "avg_pursuit_master": _r(g[6]),
            "applied_count": g[3], "above_threshold_count": g[4],
            "quality_score": _quality(a1d, g[3], g[0]),
        })

    out.sort(key=lambda r: (r["quality_score"] is not None, r["quality_score"] or 0), reverse=True)
    return out


@router.post("/feeds", response_model=FeedRead, status_code=status.HTTP_201_CREATED)
async def create_feed(
    body: FeedCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Add a custom feed (RSS URL or Apify actor)."""
    if body.feed_type not in ("rss", "apify"):
        raise HTTPException(status_code=400, detail="feed_type must be 'rss' or 'apify'")

    feed = UserFeed(
        user_id=user.id,
        feed_type=body.feed_type,
        name=body.name,
        url_or_actor=body.url_or_actor,
        actor_name=body.actor_name,
        keywords=body.keywords,
        location=body.location,
        date_range_days=body.date_range_days,
        is_platform=False,
        is_active=True,
        # V2: link to the domain CV the feed was built from (user-created, so
        # is_auto_generated stays False)
        domain_cv_id=body.domain_cv_id,
        search_keywords=body.search_keywords,
    )
    session.add(feed)
    await session.commit()
    await session.refresh(feed)
    return FeedRead.model_validate(feed)


@router.patch("/feeds/{feed_id}", response_model=FeedRead)
async def update_feed(
    feed_id: uuid.UUID,
    body: FeedUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Update feed config or toggle active state."""
    result = await session.execute(
        select(UserFeed).where(UserFeed.id == feed_id, UserFeed.user_id == user.id)
    )
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    # exclude_unset → only apply fields the client actually sent (proper PATCH;
    # also lets domain_cv_id be cleared by sending null)
    updates = body.model_dump(exclude_unset=True)
    # Platform feeds: the URL/actor is platform-managed — never overwrite it
    if feed.is_platform:
        updates.pop("url_or_actor", None)
    for field, value in updates.items():
        setattr(feed, field, value)

    await session.commit()
    await session.refresh(feed)
    return FeedRead.model_validate(feed)


@router.post("/feeds/{feed_id}/toggle")
async def toggle_feed(
    feed_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Enable or disable a feed."""
    result = await session.execute(
        select(UserFeed).where(UserFeed.id == feed_id, UserFeed.user_id == user.id)
    )
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    feed.is_active = not feed.is_active
    await session.commit()
    return {"id": str(feed_id), "is_active": feed.is_active}


@router.delete("/feeds/{feed_id}")
async def delete_feed(
    feed_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete a custom feed (platform feeds cannot be deleted)."""
    result = await session.execute(
        select(UserFeed).where(UserFeed.id == feed_id, UserFeed.user_id == user.id)
    )
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    if feed.is_platform:
        raise HTTPException(status_code=400, detail="Platform feeds cannot be deleted")

    await session.delete(feed)
    await session.commit()
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════
# TARGET COMPANIES
# ══════════════════════════════════════════════════════════════

@router.get("/companies", response_model=List[TargetCompanyRead])
async def list_target_companies(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(UserTargetCompany)
        .where(UserTargetCompany.user_id == user.id)
        .order_by(UserTargetCompany.market, UserTargetCompany.company_name)
    )
    return [TargetCompanyRead.model_validate(c) for c in result.scalars().all()]


@router.post("/companies", response_model=TargetCompanyRead, status_code=status.HTTP_201_CREATED)
async def add_target_company(
    body: TargetCompanyCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    company = UserTargetCompany(
        user_id=user.id,
        company_name=body.company_name,
        career_page_url=body.career_page_url,
        market=body.market,
        is_platform=False,
        is_active=True,
    )
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return TargetCompanyRead.model_validate(company)


@router.delete("/companies/{company_id}")
async def remove_target_company(
    company_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(UserTargetCompany).where(
            UserTargetCompany.id == company_id,
            UserTargetCompany.user_id == user.id,
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if company.is_platform:
        raise HTTPException(status_code=400, detail="Platform companies cannot be removed")

    await session.delete(company)
    await session.commit()
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════
# SCANNER CONTROL
# ══════════════════════════════════════════════════════════════

@router.post("/feeds/{feed_id}/run", dependencies=[Depends(require_active_subscription)])
async def run_single_feed(
    feed_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Run ONE feed immediately (synchronous) for the current user and return
    {jobs_found, jobs_added, duration_seconds}. RSS is fast; Apify can take a
    while (the actor run), so the client should expect a slower response."""
    from app.models.user import UserCredentials
    from app.utils.encryption import decrypt_if_present
    from app.config import settings
    from app.tasks.scanner_tasks import _scan_feeds_for_user

    feed = (await session.execute(
        select(UserFeed).where(UserFeed.id == feed_id, UserFeed.user_id == user.id)
    )).scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    creds = (await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )).scalar_one_or_none()
    apify_token = (decrypt_if_present(creds.apify_token_enc) if creds and creds.apify_token_enc else None) \
        or settings.platform_apify_token
    anthropic_key = (decrypt_if_present(creds.anthropic_api_key_enc) if creds and creds.anthropic_api_key_enc else None) \
        or settings.platform_anthropic_api_key or settings.anthropic_api_key

    started = datetime.now(timezone.utc)
    found, added, _feed_stats, _rag_stats = await _scan_feeds_for_user(user, [feed], apify_token, anthropic_key, session)
    duration = (datetime.now(timezone.utc) - started).total_seconds()

    # Usage for this feed run (set_usage_user inside _scan_feeds_for_user reset the session).
    from app.utils.usage_logger import get_session_usage
    from app.models.usage import APIUsageLog
    _u = get_session_usage()
    apify_rows = (await session.execute(select(APIUsageLog).where(
        APIUsageLog.user_id == user.id, APIUsageLog.provider == "apify",
        APIUsageLog.created_at >= started))).scalars().all()
    apify_runs = sum(r.runs_returned or 0 for r in apify_rows)
    apify_cost = round(sum(r.estimated_cost_usd or 0 for r in apify_rows), 3)
    return {"jobs_found": found, "jobs_added": added, "duration_seconds": round(duration, 1),
            "tokens_used": _u["tokens"] or None, "cost_inr": round(_u["cost_inr"], 2) or None,
            "apify_runs": apify_runs or None, "apify_cost": apify_cost or None}


@router.post("/scanner/run", dependencies=[Depends(require_active_subscription)])
async def trigger_scan(
    response: Response,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Manually trigger weekly scan.
    Runs async via Celery — returns immediately with task ID.
    """
    from app.utils.rate_limiter import enforce_rate_limit
    _rl = await enforce_rate_limit(user.id, "scanner_run_manual", session)
    response.headers["X-RateLimit-Remaining"] = str(_rl["remaining"])
    from app.tasks.scanner_tasks import weekly_job_scan
    task = weekly_job_scan.delay()
    return {
        "task_id": task.id,
        "status": "queued",
        "message": "Scan started. Check /scanner/status for progress.",
    }


@router.get("/scanner/status")
async def scanner_status(
    limit: int = 5,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get last N scan run logs."""
    result = await session.execute(
        select(RunLog)
        .where(RunLog.run_type == RunType.weekly_scan)
        .order_by(RunLog.started_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "status": log.status,
            "jobs_found": log.jobs_found,
            "jobs_added": log.jobs_added,
            "started_at": log.started_at,
            "completed_at": log.completed_at,
            "duration_seconds": log.duration_seconds,
            "details": log.details,   # V3: {feeds_run, feeds_summary:[...]}
            "error": log.error_message,
        }
        for log in logs
    ]

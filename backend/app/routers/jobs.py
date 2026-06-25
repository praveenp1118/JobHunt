"""
Jobs router — add jobs from all 5 sources, manage tracker, update status.

Sources handled here: manual paste, URL fetch, file upload
Gmail: Phase 7 (gmail_mcp)
Apify: Phase 8 (apify_mcp)
"""
import uuid
import json
import hashlib
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

from app.database import get_db
from app.config import settings
from app.models.user import User, UserCredentials, UserPlan, UserPreferences
from app.models.job import Job, EmailThread, JobStatus, JobSource
from app.models.cv import MasterCV, DomainCV
from app.models.domain import IndustryVertical, FunctionalDiscipline
from app.auth.dependencies import current_active_user
from app.utils.cv_parser import parse_file_to_text
from app.utils.encryption import decrypt_if_present
from app.utils.model import get_user_model
from app.agents.jd_agents import (
    parse_and_score_jd,
    pre_filter_jd,
    build_user_keywords,
    compute_jd_hash,
    detect_market_from_text,
    detect_language,
    fetch_url_content,
)
from app.schemas.job import (
    JobRead, JobSummary, JobFromText, JobFromURL, JobConfirm,
    JobStatusUpdate, JobUpdate, JDParseResult, EmailThreadRead,
)

router = APIRouter()

# Temp store for parsed JDs awaiting confirmation (in-memory, fine for now)
# Key: temp_id, Value: {raw_text, parsed_data, s1_score}
_parse_cache: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_anthropic_key(user: User, session: AsyncSession) -> Optional[str]:
    if user.plan == UserPlan.default:
        result = await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id)
        )
        creds = result.scalar_one_or_none()
        if creds and creds.anthropic_api_key_enc:
            return decrypt_if_present(creds.anthropic_api_key_enc)
    return settings.platform_anthropic_api_key or settings.anthropic_api_key


async def _get_master_cv(user: User, session: AsyncSession) -> Optional[MasterCV]:
    result = await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )
    return result.scalar_one_or_none()


async def _get_user_prefs(user: User, session: AsyncSession):
    from app.models.user import UserPreferences
    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    return result.scalar_one_or_none()


async def _check_duplicate(jd_hash: str, user_id: uuid.UUID, session: AsyncSession) -> Optional[Job]:
    result = await session.execute(
        select(Job).where(Job.jd_hash == jd_hash, Job.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _enrich_job(job: Job, session: AsyncSession) -> JobRead:
    """Add labels from related tables."""
    item = JobRead.model_validate(job)
    if job.industry_id:
        r = await session.execute(select(IndustryVertical).where(IndustryVertical.id == job.industry_id))
        ind = r.scalar_one_or_none()
        if ind:
            item.industry_label = ind.label
    if job.function_id:
        r = await session.execute(select(FunctionalDiscipline).where(FunctionalDiscipline.id == job.function_id))
        fn = r.scalar_one_or_none()
        if fn:
            item.function_label = fn.label
    if job.domain_cv_id:
        r = await session.execute(select(DomainCV).where(DomainCV.id == job.domain_cv_id))
        dcv = r.scalar_one_or_none()
        if dcv:
            item.domain_cv_label = f"{dcv.country_code} domain CV"
    return item


# ══════════════════════════════════════════════════════════════
# SOURCE 1: MANUAL PASTE
# ══════════════════════════════════════════════════════════════

@router.post("/parse/text", response_model=JDParseResult)
async def parse_jd_from_text(
    body: JobFromText,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Step 1: Parse JD from pasted text.
    Returns structured parse result + S1 score for user to review.
    Does NOT save yet — user confirms with POST /jobs/confirm/{temp_id}.
    """
    return await _parse_raw_text(
        raw_text=body.raw_text,
        source=JobSource.manual,
        user=user,
        session=session,
        score=body.score_immediately,
    )


# ══════════════════════════════════════════════════════════════
# SOURCE 2: URL FETCH
# ══════════════════════════════════════════════════════════════

@router.post("/parse/url", response_model=JDParseResult)
async def parse_jd_from_url(
    body: JobFromURL,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Step 1: Fetch JD from URL and parse it.
    Falls back gracefully if fetch fails.
    """
    try:
        raw_text = await fetch_url_content(body.url)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not fetch URL: {e}. Please paste the JD text manually instead.",
        )

    return await _parse_raw_text(
        raw_text=raw_text,
        source=JobSource.url,
        user=user,
        session=session,
        score=body.score_immediately,
    )


# ══════════════════════════════════════════════════════════════
# SOURCE 3: FILE UPLOAD
# ══════════════════════════════════════════════════════════════

@router.post("/parse/file", response_model=JDParseResult)
async def parse_jd_from_file(
    file: UploadFile = File(...),
    score_immediately: bool = Form(True),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Step 1: Parse JD from uploaded PDF or DOCX file.
    Multiple files = multiple separate calls to this endpoint.
    """
    file_bytes = await file.read()
    raw_text, _ = await parse_file_to_text(
        file_bytes, file.content_type or "", file.filename or ""
    )
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    return await _parse_raw_text(
        raw_text=raw_text,
        source=JobSource.file,
        user=user,
        session=session,
        score=score_immediately,
    )


# ══════════════════════════════════════════════════════════════
# CONFIRM + SAVE
# ══════════════════════════════════════════════════════════════

@router.post("/confirm/{temp_id}", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def confirm_and_save_job(
    temp_id: str,
    body: JobConfirm,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Step 2: User has reviewed parsed fields, now save the job.
    User can edit any field before confirming.
    """
    cached = _parse_cache.get(temp_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="Parse session expired or not found. Please re-parse the JD.",
        )

    # Check duplicate again (in case user confirmed after a delay)
    jd_hash = cached.get("jd_hash")
    existing = await _check_duplicate(jd_hash, user.id, session) if jd_hash else None
    if existing:
        return await _enrich_job(existing, session)

    # Map parsed industry/function to DB IDs if available
    industry_id = None
    function_id = None
    parsed = cached.get("parsed", {})

    # Create job record
    job = Job(
        user_id=user.id,
        company=body.company,
        role=body.role,
        location=body.location or parsed.get("location"),
        market=body.market or parsed.get("market") or detect_market_from_text(
            f"{body.location} {body.company}"
        ),
        jd_hash=jd_hash,
        jd_raw=cached.get("raw_text", "")[:50000],  # cap at 50KB
        jd_md=body.jd_md or cached.get("raw_text", "")[:50000],
        jd_language=parsed.get("jd_language", "en"),
        recruiter_email=body.recruiter_email or parsed.get("recruiter_email"),
        portal_url=body.portal_url,
        source=cached.get("source", JobSource.manual),
        status=JobStatus.new,
        s1=cached.get("s1_score"),
        s1_tokens=cached.get("s1_tokens"),
        s1_cost_inr=cached.get("s1_cost_inr"),
        salary_range_raw=parsed.get("comp_range"),
        notes=body.notes,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    # Clean up cache
    _parse_cache.pop(temp_id, None)

    return await _enrich_job(job, session)


@router.post("/save-direct", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def save_job_direct(
    body: JobConfirm,
    raw_text: str = "",
    source: JobSource = JobSource.manual,
    s1_score: Optional[float] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Direct save — used by Gmail and Apify importers who already have structured data.
    """
    jd_hash = compute_jd_hash(raw_text) if raw_text else None

    if jd_hash:
        existing = await _check_duplicate(jd_hash, user.id, session)
        if existing:
            return await _enrich_job(existing, session)

    job = Job(
        user_id=user.id,
        company=body.company,
        role=body.role,
        location=body.location,
        market=body.market or detect_market_from_text(f"{body.location or ''} {body.company}"),
        jd_hash=jd_hash,
        jd_raw=raw_text[:50000] if raw_text else None,
        jd_md=raw_text[:50000] if raw_text else None,
        recruiter_email=body.recruiter_email,
        portal_url=body.portal_url,
        source=source,
        status=JobStatus.new,
        s1=s1_score,
        notes=body.notes,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return await _enrich_job(job, session)


# ══════════════════════════════════════════════════════════════
# TRACKER: LIST + DETAIL + UPDATE
# ══════════════════════════════════════════════════════════════

@router.get("")
async def list_jobs(
    status_filter: Optional[List[JobStatus]] = Query(None, alias="status"),
    market: Optional[List[str]] = Query(None),
    source: Optional[List[JobSource]] = Query(None),
    needs_hitl: Optional[bool] = None,
    min_s1: Optional[float] = None,
    score: Optional[float] = None,   # min effective score (coalesce s1d, s1)
    domain: Optional[str] = None,    # best_domain_cv_id
    search: Optional[str] = None,
    sort: Optional[str] = None,       # best_fit | s1 | company | role | market | status | source | created_at
    order: str = "desc",             # asc | desc
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """List jobs with filters. Returns the page plus total_count (matching the
    current filters) and unfiltered_count (all of the user's jobs).

    Sorting is applied server-side BEFORE pagination so the correct rows reach the
    page (a high-s1d job that sits beyond the page limit by created_at must still
    surface at the top when sorting by Best Fit)."""
    from sqlalchemy import func, nullslast

    filters = [Job.user_id == user.id]
    if status_filter:
        filters.append(Job.status.in_(status_filter))
    if market:
        filters.append(Job.market.in_(market))
    if source:
        filters.append(Job.source.in_(source))
    if needs_hitl is not None:
        filters.append(Job.needs_hitl == needs_hitl)
    if min_s1 is not None:
        filters.append(Job.s1 >= min_s1)
    if score is not None:
        # score filter uses the best domain fit when present, else base fit
        filters.append(func.coalesce(Job.s1d, Job.s1) >= score)
    if domain:
        try:
            filters.append(Job.best_domain_cv_id == uuid.UUID(domain))
        except (ValueError, TypeError):
            pass
    if search:
        filters.append(or_(
            Job.company.ilike(f"%{search}%"),
            Job.role.ilike(f"%{search}%"),
        ))

    total_count = (await session.execute(
        select(func.count(Job.id)).where(*filters)
    )).scalar() or 0
    unfiltered_count = (await session.execute(
        select(func.count(Job.id)).where(Job.user_id == user.id)
    )).scalar() or 0

    # ── Ordering (server-side, before pagination) ──
    sort_map = {
        "best_fit": Job.s1d,                 # Best Fit column = best domain-CV score
        "s1": Job.s1,
        "company": func.lower(Job.company),
        "role": func.lower(Job.role),
        "market": Job.market,
        "status": Job.status,
        "source": Job.source,
        "created_at": Job.created_at,
    }
    sort_key = sort if sort in sort_map else "created_at"
    col = sort_map[sort_key]
    primary = col.asc() if order.lower() == "asc" else col.desc()
    if sort_key in ("best_fit", "s1"):
        primary = nullslast(primary)         # unscored jobs always sink to the bottom
    order_clauses = [primary]
    if sort_key != "created_at":
        order_clauses.append(Job.created_at.desc())  # stable tiebreaker (same score → newest first)

    result = await session.execute(
        select(Job).where(*filters).order_by(*order_clauses).offset(skip).limit(limit)
    )
    jobs = result.scalars().all()

    # Human-readable labels for every domain CV the user has, so the frontend can
    # resolve domain_cv_scores / best_domain_cv_id ids → "Industry × Country".
    dcv_rows = (await session.execute(
        select(DomainCV.id, IndustryVertical.label, DomainCV.country_code)
        .outerjoin(IndustryVertical, IndustryVertical.id == DomainCV.industry_id)
        .where(DomainCV.user_id == user.id)
    )).all()
    label_map = {str(did): f"{ind or 'Domain'} × {cc or '—'}" for did, ind, cc in dcv_rows}

    # Community availability — one query for all shared insights (≥2 contributors),
    # matched to the page's jobs by company + normalized role.
    from app.models.community import CommunityJobInsight
    from app.utils.community import normalize_role, normalize_company
    comm_rows = (await session.execute(
        select(CommunityJobInsight.company, CommunityJobInsight.role_normalized,
               CommunityJobInsight.contributor_count)
        .where(CommunityJobInsight.contributor_count >= 2)
    )).all()
    comm_map = {(c, r): cc for c, r, cc in comm_rows}

    summaries = []
    for j in jobs:
        s = JobSummary.model_validate(j)
        ids = set((j.domain_cv_scores or {}).keys())
        if j.best_domain_cv_id:
            ids.add(str(j.best_domain_cv_id))
        if ids:
            s.domain_cv_labels = {i: label_map.get(i, "Domain") for i in ids}
        cc = comm_map.get((normalize_company(j.company or ""), normalize_role(j.role or "")))
        if cc:
            s.community_available = True
            s.community_contributors = cc
        summaries.append(s)
    return {"jobs": summaries, "total_count": total_count, "unfiltered_count": unfiltered_count}


@router.get("/stats")
async def get_job_stats(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Pipeline counts for Dashboard — V2: includes by_source and by_domain_cv."""
    from sqlalchemy import func
    from app.models.cv import DomainCV

    # Status counts
    result = await session.execute(
        select(Job.status, func.count(Job.id))
        .where(Job.user_id == user.id)
        .group_by(Job.status)
    )
    counts = {row[0]: row[1] for row in result}

    # Source counts (manual vs scan)
    source_result = await session.execute(
        select(Job.source, func.count(Job.id))
        .where(Job.user_id == user.id)
        .group_by(Job.source)
    )
    by_source = {str(row[0].value if hasattr(row[0], 'value') else row[0]): row[1] for row in source_result}

    # Scan-sourced jobs (rss + apify)
    from_scan = by_source.get('rss', 0) + by_source.get('apify', 0)

    # By domain CV
    domain_result = await session.execute(
        select(Job.detected_domain_cv_id, func.count(Job.id))
        .where(Job.user_id == user.id, Job.detected_domain_cv_id != None)
        .group_by(Job.detected_domain_cv_id)
    )
    by_domain_raw = {str(row[0]): row[1] for row in domain_result}

    # Enrich domain CV labels
    by_domain_cv = []
    for dcv_id, count in by_domain_raw.items():
        dcv_result = await session.execute(
            select(DomainCV).where(DomainCV.id == dcv_id)
        )
        dcv = dcv_result.scalar_one_or_none()
        label = "Unknown"
        if dcv:
            ind = ""
            fn = ""
            if dcv.industry_id:
                from app.models.domain import IndustryVertical
                ind_r = await session.execute(select(IndustryVertical).where(IndustryVertical.id == dcv.industry_id))
                ind_obj = ind_r.scalar_one_or_none()
                if ind_obj: ind = ind_obj.label
            if dcv.function_id:
                from app.models.domain import FunctionalDiscipline
                fn_r = await session.execute(select(FunctionalDiscipline).where(FunctionalDiscipline.id == dcv.function_id))
                fn_obj = fn_r.scalar_one_or_none()
                if fn_obj: fn = fn_obj.label
            label = f"{ind} × {fn}" if ind and fn else (ind or fn or "Domain CV")
        by_domain_cv.append({"label": label, "count": count, "domain_cv_id": dcv_id})

    # By best-fit domain CV (drives the Domain filter dropdown counts)
    bd_result = await session.execute(
        select(Job.best_domain_cv_id, func.count(Job.id))
        .where(Job.user_id == user.id, Job.best_domain_cv_id != None)
        .group_by(Job.best_domain_cv_id)
    )
    by_best_domain = {str(row[0]): row[1] for row in bd_result}

    # S1 score distribution (legacy buckets, on s1)
    score_result = await session.execute(
        select(Job.s1).where(Job.user_id == user.id, Job.s1 != None)
    )
    scores = [row[0] for row in score_result]
    score_dist = {
        "excellent": sum(1 for s in scores if s >= 85),
        "good": sum(1 for s in scores if 70 <= s < 85),
        "fair": sum(1 for s in scores if 55 <= s < 70),
        "low": sum(1 for s in scores if s < 55),
    }

    # Score buckets for the Score filter pills — use s1d when present, else s1.
    eff_result = await session.execute(
        select(func.coalesce(Job.s1d, Job.s1)).where(Job.user_id == user.id)
    )
    eff = [row[0] for row in eff_result if row[0] is not None]
    total = sum(counts.values())
    by_score_bucket = {
        "any": total,
        "gte_70": sum(1 for s in eff if s >= 70),
        "gte_80": sum(1 for s in eff if s >= 80),
        "gte_90": sum(1 for s in eff if s >= 90),
    }

    # Needs-HITL count (a boolean flag, not a status)
    needs_hitl = (await session.execute(
        select(func.count(Job.id)).where(Job.user_id == user.id, Job.needs_hitl == True)
    )).scalar() or 0

    return {
        "total": total,
        "by_status": {s.value: counts.get(s, 0) for s in JobStatus},
        "needs_hitl": needs_hitl,
        "from_scan": from_scan,
        "by_source": by_source,
        "by_domain_cv": by_domain_cv,
        "by_best_domain": by_best_domain,
        "by_score_bucket": by_score_bucket,
        "score_distribution": score_dist,
        "avg_s1": round(sum(scores) / len(scores), 1) if scores else None,
    }


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get full job detail."""
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return await _enrich_job(job, session)


@router.patch("/{job_id}/status", response_model=JobRead)
async def update_job_status(
    job_id: uuid.UUID,
    body: JobStatusUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Update job status (e.g. New → Applied, Applied → Interview R1)."""
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = body.status
    if body.notes:
        job.notes = body.notes
    if body.status == JobStatus.applied and not job.applied_at:
        job.applied_at = datetime.now(timezone.utc)

    await session.commit()

    # Opt-in community insights when a job is marked Applied (never blocks the update).
    if body.status == JobStatus.applied:
        from app.utils.community import maybe_share_on_apply
        await maybe_share_on_apply(session, user, job)

    await session.refresh(job)
    return await _enrich_job(job, session)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: uuid.UUID,
    body: JobUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Update job fields (recruiter email, interview details, etc.)."""
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(job, field, value)

    await session.commit()
    await session.refresh(job)
    return await _enrich_job(job, session)


@router.delete("/{job_id}")
async def delete_job(
    job_id: uuid.UUID,
    confirm: bool = Query(False),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete a job. Requires confirm=true (two-step from UI).
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Add ?confirm=true to confirm deletion",
        )
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await session.delete(job)
    await session.commit()
    return {"deleted": True}


@router.get("/{job_id}/emails", response_model=List[EmailThreadRead])
async def get_job_emails(
    job_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Email thread for a job application."""
    result = await session.execute(
        select(EmailThread)
        .where(EmailThread.job_id == job_id, EmailThread.user_id == user.id)
        .order_by(EmailThread.created_at)
    )
    return [EmailThreadRead.model_validate(e) for e in result.scalars().all()]


@router.post("/{job_id}/fetch-jd")
async def fetch_full_jd(
    job_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Queue a background fetch of the full JD (from portal_url) + re-score for a
    partial-JD (gmail_alert) job. Returns immediately; the tracker refreshes when done."""
    job = (await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.portal_url:
        raise HTTPException(status_code=400, detail="No portal URL to fetch the full JD from")
    from app.tasks.gmail_tasks import fetch_partial_jd
    fetch_partial_jd.delay(str(job_id), str(user.id))
    return {"status": "queued"}


@router.post("/{job_id}/score-s1")
async def score_job_s1(
    job_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Manually trigger S1 scoring for a job."""
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.jd_raw:
        raise HTTPException(status_code=400, detail="No JD content to score against")

    master = await _get_master_cv(user, session)
    if not master:
        raise HTTPException(status_code=400, detail="Upload your master CV first")

    anthropic_key = await _get_anthropic_key(user, session)
    result_data = await parse_and_score_jd(job.jd_raw, master.content_md, anthropic_key)

    job.s1 = result_data["s1_score"]
    await session.commit()
    return {"s1_score": job.s1, "key_matches": result_data["key_matches"], "gaps": result_data["gaps"]}


# ══════════════════════════════════════════════════════════════
# SHARED PARSE LOGIC
# ══════════════════════════════════════════════════════════════

async def _parse_raw_text(
    raw_text: str,
    source: JobSource,
    user: User,
    session: AsyncSession,
    score: bool = True,
) -> JDParseResult:
    """
    Shared logic for all parse endpoints.
    1. Pre-filter (rule-based)
    2. Check duplicate
    3. Parse + score (one Claude call)
    4. Cache result, return preview
    """
    # Pre-filter
    prefs = await _get_user_prefs(user, session)
    target_roles = prefs.target_roles if prefs else None
    filter_result = pre_filter_jd(raw_text, user_keywords=build_user_keywords(target_roles))

    # Hash for dedup
    jd_hash = compute_jd_hash(raw_text)
    existing = await _check_duplicate(jd_hash, user.id, session)
    if existing:
        return JDParseResult(
            temp_id="",
            company=existing.company,
            role=existing.role,
            location=existing.location,
            market=existing.market,
            seniority=None,
            remote_policy=None,
            required_skills=[],
            preferred_skills=[],
            comp_range=existing.salary_range_raw,
            recruiter_email=existing.recruiter_email,
            jd_language=existing.jd_language,
            s1_score=existing.s1 or 0,
            key_matches=[],
            gaps=[],
            pre_filter_passed=filter_result["passed"],
            pre_filter_reason=filter_result.get("reason_code"),
            is_duplicate=True,
            existing_job_id=existing.id,
        )

    # Parse + score via Claude (or skip if pre-filter failed)
    parsed_data = {}
    s1_score = 0.0
    key_matches: list = []
    gaps: list = []
    s1_tokens = None
    s1_cost_inr = None

    if score and filter_result["passed"]:
        master = await _get_master_cv(user, session)
        if master:
            anthropic_key = await _get_anthropic_key(user, session)
            from app.utils.usage_logger import set_usage_user, set_usage_entity, get_session_usage
            set_usage_user(user.id)
            set_usage_entity("job", None, None)
            result_data = await parse_and_score_jd(raw_text, master.content_md, anthropic_key)
            parsed_data = result_data.get("parsed", {})
            s1_score = result_data.get("s1_score", 0)
            key_matches = result_data.get("key_matches", [])
            gaps = result_data.get("gaps", [])
            _pu = get_session_usage()
            s1_tokens = _pu["tokens"] or None
            s1_cost_inr = round(_pu["cost_inr"], 2) or None
        else:
            # No master CV — parse only, no scoring
            parsed_data = {
                "company": "Unknown",
                "role": "Unknown",
                "market": detect_market_from_text(raw_text),
                "jd_language": detect_language(raw_text),
            }
    else:
        # Pre-filter failed or scoring disabled — minimal parse
        parsed_data = {
            "company": "Unknown",
            "role": "Unknown",
            "market": detect_market_from_text(raw_text),
            "jd_language": detect_language(raw_text),
        }

    # Cache for confirmation step
    temp_id = str(uuid.uuid4())
    _parse_cache[temp_id] = {
        "raw_text": raw_text,
        "jd_hash": jd_hash,
        "parsed": parsed_data,
        "s1_score": s1_score,
        "s1_tokens": s1_tokens,
        "s1_cost_inr": s1_cost_inr,
        "source": source,
    }

    return JDParseResult(
        temp_id=temp_id,
        company=parsed_data.get("company") or "Unknown",
        role=parsed_data.get("role") or "Unknown",
        location=parsed_data.get("location"),
        market=parsed_data.get("market"),
        seniority=parsed_data.get("seniority"),
        remote_policy=parsed_data.get("remote_policy"),
        required_skills=parsed_data.get("required_skills", []),
        preferred_skills=parsed_data.get("preferred_skills", []),
        comp_range=parsed_data.get("comp_range"),
        recruiter_email=parsed_data.get("recruiter_email"),
        jd_language=parsed_data.get("jd_language") or "en",
        s1_score=s1_score,
        key_matches=key_matches,
        gaps=gaps,
        pre_filter_passed=filter_result["passed"],
        pre_filter_reason=filter_result.get("reason_code"),
        is_duplicate=False,
        s1_tokens=s1_tokens,
        s1_cost_inr=s1_cost_inr,
    )

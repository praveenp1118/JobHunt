"""
CV router — master CV, domain CVs, change log, S3 scoring.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import settings
from app.models.user import User, UserCredentials, UserPlan
from app.models.cv import (
    MasterCV, MasterCVVersion, DomainCV, DomainCVVersion, ChangeLog,
    CVStatus, ChangeType, ChangeStatus
)
from app.models.domain import IndustryVertical, FunctionalDiscipline, CountryMaster
from app.auth.dependencies import current_active_user
from app.utils.subscription import require_active_subscription
from app.utils.cv_parser import parse_file_to_text, count_words
from app.utils.storage import (
    save_text_file, read_text_file,
    cv_master_path, cv_domain_path,
)
from app.utils.encryption import decrypt_if_present
from app.utils.model import get_user_model
from app.schemas.cv import (
    MasterCVRead, MasterCVVersionRead, MasterCVUpdate,
    DomainCVCreate, DomainCVRead, DomainCVVersionRead,
    ChangeLogItemRead, ChangeLogEdit, ChangeLogBulkAction,
    S3ScoreResult,
)
from app.agents.cv_agents import (
    text_to_markdown_cv,
    generate_domain_changelog,
    apply_changes,
    compute_s3_score,
)

router = APIRouter()


# ── Helper: get user's Anthropic key ─────────────────────────────────────────

async def _get_anthropic_key(user: User, session: AsyncSession) -> Optional[str]:
    """Get the appropriate Anthropic API key for this user."""
    if user.plan == UserPlan.default:
        result = await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id)
        )
        creds = result.scalar_one_or_none()
        if creds and creds.anthropic_api_key_enc:
            return decrypt_if_present(creds.anthropic_api_key_enc)
    return settings.platform_anthropic_api_key or settings.anthropic_api_key


# ══════════════════════════════════════════════════════════════
# MASTER CV
# ══════════════════════════════════════════════════════════════

@router.get("/master", response_model=Optional[MasterCVRead])
async def get_master_cv(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get the current master CV."""
    result = await session.execute(
        select(MasterCV)
        .where(MasterCV.user_id == user.id, MasterCV.is_active == True)
        .order_by(MasterCV.version.desc())
    )
    master = result.scalar_one_or_none()
    return MasterCVRead.model_validate(master) if master else None


@router.post("/master/upload", response_model=MasterCVRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_active_subscription)])
async def upload_master_cv(
    file: UploadFile = File(...),
    change_summary: Optional[str] = Form(None),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Upload master CV from file (PDF or DOCX).
    Claude converts to clean markdown.
    Previous version saved to history. Domain CVs flagged stale.
    """
    from app.utils.input_validator import validate_file_type, CV_ALLOWED_TYPES, MAX_CV_SIZE
    if not validate_file_type(file.filename or "", CV_ALLOWED_TYPES):
        raise HTTPException(status_code=400,
                            detail=f"Unsupported file type. Allowed: {', '.join(CV_ALLOWED_TYPES)}")

    anthropic_key = await _get_anthropic_key(user, session)
    from app.utils.usage_logger import set_usage_user, set_usage_entity, get_session_usage
    set_usage_user(user.id)
    set_usage_entity("master_cv", None, "Master CV")

    # Read and parse file
    file_bytes = await file.read()
    if len(file_bytes) > MAX_CV_SIZE:
        raise HTTPException(status_code=400, detail="File too large — maximum 10 MB.")
    raw_text, file_format = await parse_file_to_text(
        file_bytes, file.content_type or "", file.filename or ""
    )
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    # Convert to clean markdown via Claude
    cv_md = await text_to_markdown_cv(raw_text, anthropic_key)

    result = await _save_master_cv(
        user, session, cv_md, change_summary or f"Uploaded from {file.filename}"
    )
    _u = get_session_usage()
    result.tokens_used = _u["tokens"] or None
    result.cost_inr = round(_u["cost_inr"], 2) or None
    return result


@router.post("/master/text", response_model=MasterCVRead, status_code=status.HTTP_201_CREATED)
async def create_master_cv_from_text(
    update: MasterCVUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Create or update master CV from pasted markdown text."""
    return await _save_master_cv(
        user, session, update.content_md, update.change_summary or "Manual text update"
    )


@router.put("/master", response_model=MasterCVRead)
async def update_master_cv(
    update: MasterCVUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Inline edit — update master CV content."""
    return await _save_master_cv(
        user, session, update.content_md, update.change_summary or "Inline edit"
    )


async def _save_master_cv(
    user: User,
    session: AsyncSession,
    cv_md: str,
    change_summary: str,
) -> MasterCVRead:
    """
    Shared logic for all master CV saves.
    - Archives old version
    - Creates new version
    - Flags all domain CVs as stale
    """
    # Get or determine next version number
    result = await session.execute(
        select(MasterCV)
        .where(MasterCV.user_id == user.id, MasterCV.is_active == True)
        .order_by(MasterCV.version.desc())
    )
    existing = result.scalar_one_or_none()
    next_version = (existing.version + 1) if existing else 1

    # Archive old version to history
    if existing:
        old_version = MasterCVVersion(
            master_cv_id=existing.id,
            user_id=user.id,
            content_md=existing.content_md,
            version=existing.version,
            change_summary=change_summary,
        )
        session.add(old_version)
        existing.is_active = False
        await session.flush()

    # Create new master CV record
    master = MasterCV(
        user_id=user.id,
        content_md=cv_md,
        version=next_version,
        word_count=count_words(cv_md),
        is_active=True,
    )
    session.add(master)
    await session.flush()

    # Save to file storage
    path = cv_master_path(user.id, next_version)
    await save_text_file(cv_md, path)

    # Flag all domain CVs as stale
    domain_result = await session.execute(
        select(DomainCV).where(DomainCV.user_id == user.id)
    )
    domain_cvs = domain_result.scalars().all()
    for dcv in domain_cvs:
        if dcv.status in (CVStatus.active, CVStatus.review_required):
            dcv.status = CVStatus.stale
            dcv.master_cv_id = master.id

    await session.commit()
    await session.refresh(master)
    # Hybrid-RAG: (re)compute the CV essence (best-effort, cheap Haiku call).
    await _compute_master_essence(master, user, session)
    # The essence step commits (on success), which expires `master` — reload it in the async
    # context so the synchronous Pydantic serialization below can't trigger a lazy DB load
    # (that would raise MissingGreenlet → a spurious 500 even though the CV is saved).
    await session.refresh(master)
    return MasterCVRead.model_validate(master)


async def _compute_master_essence(master, user, session) -> bool:
    """Extract + store the master CV essence (Stage-2 input). Never breaks the save."""
    try:
        from app.models.user import UserPreferences
        from app.agents.essence_agent import extract_cv_essence
        from app.utils.usage_logger import set_usage_user
        from app.utils.subscription import is_entitled
        # Saving/editing CV markdown is free (browsing/setup), but the essence is a
        # Claude call — skip it for un-entitled users so nothing spends tokens un-paid.
        if not is_entitled(user):
            return False
        key = await _get_anthropic_key(user, session)
        if not key:
            return False
        set_usage_user(user.id)
        prefs = (await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id))).scalars().first()
        model = (prefs.s1_essence_model if prefs and prefs.s1_essence_model else "claude-haiku-4-5")
        essence = await extract_cv_essence(master.content_md, master.version, anthropic_key=key, model=model)
        master.essence_json = essence
        master.essence_computed_at = datetime.now(timezone.utc)
        master.essence_version = master.version
        await session.commit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ master essence extraction failed: {e}")
        return False


async def _compute_domain_essence(dcv, user, session) -> bool:
    """Extract + store a domain CV's essence (with domain extras). Never breaks the apply."""
    try:
        from app.models.user import UserPreferences
        from app.agents.essence_agent import extract_cv_essence
        from app.utils.usage_logger import set_usage_user
        from app.utils.subscription import is_entitled
        if not dcv.content_md:
            return False
        if not is_entitled(user):
            return False
        key = await _get_anthropic_key(user, session)
        if not key:
            return False
        set_usage_user(user.id)
        prefs = (await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id))).scalars().first()
        model = (prefs.s1_essence_model if prefs and prefs.s1_essence_model else "claude-haiku-4-5")
        ind = (await session.execute(
            select(IndustryVertical.label).where(IndustryVertical.id == dcv.industry_id))).scalar() if dcv.industry_id else None
        fn = (await session.execute(
            select(FunctionalDiscipline.label).where(FunctionalDiscipline.id == dcv.function_id))).scalar() if dcv.function_id else None
        domain_context = {"industry": ind, "function": fn, "country_code": dcv.country_code}
        essence = await extract_cv_essence(dcv.content_md, dcv.version, domain_context=domain_context,
                                           anthropic_key=key, model=model)
        dcv.essence_json = essence
        dcv.essence_computed_at = datetime.now(timezone.utc)
        await session.commit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ domain essence extraction failed: {e}")
        return False


@router.get("/master/versions", response_model=List[MasterCVVersionRead])
async def get_master_cv_versions(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Version history for master CV."""
    result = await session.execute(
        select(MasterCVVersion)
        .where(MasterCVVersion.user_id == user.id)
        .order_by(MasterCVVersion.version.desc())
    )
    return [MasterCVVersionRead.model_validate(v) for v in result.scalars().all()]


@router.post("/master/rollback/{version}", response_model=MasterCVRead)
async def rollback_master_cv(
    version: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Rollback master CV to a previous version."""
    result = await session.execute(
        select(MasterCVVersion)
        .where(MasterCVVersion.user_id == user.id, MasterCVVersion.version == version)
    )
    old_version = result.scalar_one_or_none()
    if not old_version:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    return await _save_master_cv(
        user, session, old_version.content_md, f"Rolled back to v{version}"
    )


# ══════════════════════════════════════════════════════════════
# DOMAIN CVs
# ══════════════════════════════════════════════════════════════

@router.get("/domains", response_model=List[DomainCVRead])
async def list_domain_cvs(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """List all domain CVs for the current user."""
    result = await session.execute(
        select(DomainCV)
        .where(DomainCV.user_id == user.id)
        .order_by(DomainCV.created_at.desc())
    )
    cvs = result.scalars().all()

    # Enrich with labels
    enriched = []
    for cv in cvs:
        item = DomainCVRead.model_validate(cv)
        # Get industry label
        ind_result = await session.execute(
            select(IndustryVertical).where(IndustryVertical.id == cv.industry_id)
        )
        ind = ind_result.scalar_one_or_none()
        if ind:
            item.industry_label = ind.label

        # Get function label
        fn_result = await session.execute(
            select(FunctionalDiscipline).where(FunctionalDiscipline.id == cv.function_id)
        )
        fn = fn_result.scalar_one_or_none()
        if fn:
            item.function_label = fn.label

        # Get country name
        co_result = await session.execute(
            select(CountryMaster).where(CountryMaster.country_code == cv.country_code)
        )
        co = co_result.scalar_one_or_none()
        if co:
            item.country_name = co.country_name

        enriched.append(item)

    return enriched


@router.get("/domains/{domain_cv_id}", response_model=DomainCVRead)
async def get_domain_cv(
    domain_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get a specific domain CV."""
    result = await session.execute(
        select(DomainCV)
        .where(DomainCV.id == domain_cv_id, DomainCV.user_id == user.id)
    )
    cv = result.scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="Domain CV not found")
    return DomainCVRead.model_validate(cv)


@router.post("/domains/generate-changelog", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_active_subscription)])
async def generate_domain_cv_changelog(
    body: DomainCVCreate,
    response: Response,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Step 1 of domain CV generation: generate change log.
    Creates a DomainCV in 'regenerating' status with pending change log items.
    Returns the domain_cv_id and list of proposed changes.
    """
    from app.utils.rate_limiter import enforce_rate_limit
    _rl = await enforce_rate_limit(user.id, "domain_generate", session)
    response.headers["X-RateLimit-Remaining"] = str(_rl["remaining"])

    # Check master CV exists
    master_result = await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )
    master = master_result.scalar_one_or_none()
    if not master:
        raise HTTPException(
            status_code=400,
            detail="No master CV found. Upload your master CV first."
        )

    # Load domain + function + country
    ind_result = await session.execute(
        select(IndustryVertical).where(IndustryVertical.id == body.industry_id)
    )
    industry = ind_result.scalar_one_or_none()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry vertical not found")

    fn_result = await session.execute(
        select(FunctionalDiscipline).where(FunctionalDiscipline.id == body.function_id)
    )
    function = fn_result.scalar_one_or_none()
    if not function:
        raise HTTPException(status_code=404, detail="Functional discipline not found")

    co_result = await session.execute(
        select(CountryMaster).where(CountryMaster.country_code == body.country_code)
    )
    country = co_result.scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{body.country_code}' not found")

    # Check if domain CV already exists for this combination
    existing_result = await session.execute(
        select(DomainCV).where(
            DomainCV.user_id == user.id,
            DomainCV.industry_id == body.industry_id,
            DomainCV.function_id == body.function_id,
            DomainCV.country_code == body.country_code,
        )
    )
    existing_domain_cv = existing_result.scalar_one_or_none()
    next_version = (existing_domain_cv.version + 1) if existing_domain_cv else 1

    # Create new domain CV record in 'regenerating' state
    domain_cv = DomainCV(
        user_id=user.id,
        master_cv_id=master.id,
        industry_id=body.industry_id,
        function_id=body.function_id,
        country_code=body.country_code,
        content_md="",  # filled after user approves changes
        version=next_version,
        status=CVStatus.regenerating,
    )
    session.add(domain_cv)
    await session.flush()

    # Archive old if exists
    if existing_domain_cv:
        old_ver = DomainCVVersion(
            domain_cv_id=existing_domain_cv.id,
            content_md=existing_domain_cv.content_md,
            version=existing_domain_cv.version,
            s3_domain=existing_domain_cv.s3_domain,
            s3_master=existing_domain_cv.s3_master,
            change_summary="Superseded by new version",
        )
        session.add(old_ver)
        await session.delete(existing_domain_cv)
        await session.flush()

    # Get Anthropic key
    anthropic_key = await _get_anthropic_key(user, session)

    # Generate change log via Claude
    country_rules_dict = {
        "country_name": country.country_name,
        "phone_on_cv": country.phone_on_cv,
        "remove_photo": country.remove_photo,
        "remove_dob": country.remove_dob,
        "relocation_note": country.relocation_note,
        "lines_to_add": country.lines_to_add,
    }

    user_model = await get_user_model(user.id, session)
    from app.utils.usage_logger import set_usage_entity, get_session_usage
    set_usage_entity("domain_cv", domain_cv.id, f"{industry.label} × {body.country_code}")
    changes = await generate_domain_changelog(
        master_cv_md=master.content_md,
        industry_label=industry.label,
        industry_keywords=industry.detection_keywords or "",
        industry_emphasis=industry.emphasis_rules or "",
        function_label=function.label,
        function_keywords=function.detection_keywords or "",
        country_code=body.country_code,
        country_rules=country_rules_dict,
        user_anthropic_key=anthropic_key,
    )

    # Save change log items to DB
    for change in changes:
        cl_item = ChangeLog(
            user_id=user.id,
            domain_cv_id=domain_cv.id,
            change_type=change.get("change_type", ChangeType.rephrase),
            section=change.get("section"),
            original_text=change.get("original_text"),
            proposed_text=change.get("proposed_text"),
            reason=change.get("reason"),
            status=ChangeStatus.pending,
        )
        session.add(cl_item)

    await session.commit()
    await session.refresh(domain_cv)

    _u = get_session_usage()
    return {
        "domain_cv_id": str(domain_cv.id),
        "version": domain_cv.version,
        "change_count": len(changes),
        "changes": changes,
        "message": f"Generated {len(changes)} proposed changes. Review and approve each one.",
        "tokens_used": _u["tokens"] or None,
        "cost_inr": round(_u["cost_inr"], 2) or None,
    }


@router.get("/domains/{domain_cv_id}/changelog", response_model=List[ChangeLogItemRead])
async def get_domain_cv_changelog(
    domain_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get the change log for a domain CV."""
    result = await session.execute(
        select(ChangeLog)
        .where(ChangeLog.domain_cv_id == domain_cv_id, ChangeLog.user_id == user.id)
        .order_by(ChangeLog.created_at)
    )
    return [ChangeLogItemRead.model_validate(c) for c in result.scalars().all()]


@router.post("/domains/{domain_cv_id}/changelog/{change_id}/approve")
async def approve_change(
    domain_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Approve a change log item as-is."""
    change = await _get_change(domain_cv_id, change_id, user.id, session)
    change.status = ChangeStatus.approved
    change.final_text = change.proposed_text
    await session.commit()
    return {"status": "approved"}


@router.put("/domains/{domain_cv_id}/changelog/{change_id}/edit")
async def edit_and_approve_change(
    domain_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    body: ChangeLogEdit,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Edit a change and approve the edited version."""
    change = await _get_change(domain_cv_id, change_id, user.id, session)
    change.status = ChangeStatus.approved_edited
    change.final_text = body.final_text
    await session.commit()
    return {"status": "approved_edited", "final_text": body.final_text}


@router.post("/domains/{domain_cv_id}/changelog/{change_id}/reject")
async def reject_change(
    domain_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Reject a change log item."""
    change = await _get_change(domain_cv_id, change_id, user.id, session)
    change.status = ChangeStatus.rejected
    await session.commit()
    return {"status": "rejected"}


@router.post("/domains/{domain_cv_id}/changelog/bulk")
async def bulk_change_action(
    domain_cv_id: uuid.UUID,
    body: ChangeLogBulkAction,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Bulk approve or reject all pending changes."""
    if body.action not in ("approve_all", "reject_all"):
        raise HTTPException(status_code=400, detail="action must be approve_all or reject_all")

    result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.domain_cv_id == domain_cv_id,
            ChangeLog.user_id == user.id,
            ChangeLog.status == ChangeStatus.pending,
        )
    )
    changes = result.scalars().all()

    for change in changes:
        if body.action == "approve_all":
            change.status = ChangeStatus.approved
            change.final_text = change.proposed_text
        else:
            change.status = ChangeStatus.rejected

    await session.commit()
    return {"updated": len(changes), "action": body.action}


@router.post("/domains/{domain_cv_id}/apply", response_model=DomainCVRead,
             dependencies=[Depends(require_active_subscription)])
async def apply_domain_cv_changes(
    domain_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Step 2 of domain CV generation: apply approved changes, compute S3, save.
    Only runs after user has reviewed the change log.
    """
    # Load domain CV
    dcv_result = await session.execute(
        select(DomainCV).where(DomainCV.id == domain_cv_id, DomainCV.user_id == user.id)
    )
    domain_cv = dcv_result.scalar_one_or_none()
    if not domain_cv:
        raise HTTPException(status_code=404, detail="Domain CV not found")

    # Load master CV
    master_result = await session.execute(
        select(MasterCV).where(MasterCV.id == domain_cv.master_cv_id)
    )
    master = master_result.scalar_one_or_none()
    if not master:
        raise HTTPException(status_code=400, detail="Master CV not found")

    # Load country rules
    co_result = await session.execute(
        select(CountryMaster).where(CountryMaster.country_code == domain_cv.country_code)
    )
    country = co_result.scalar_one_or_none()
    country_rules = {
        "country_name": country.country_name if country else domain_cv.country_code,
        "phone_on_cv": country.phone_on_cv if country else True,
        "remove_photo": country.remove_photo if country else False,
        "remove_dob": country.remove_dob if country else False,
        "relocation_note": country.relocation_note if country else None,
        "lines_to_add": country.lines_to_add if country else "[]",
    }

    # Load approved changes
    cl_result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.domain_cv_id == domain_cv_id,
            ChangeLog.status.in_([ChangeStatus.approved, ChangeStatus.approved_edited]),
        )
    )
    approved = cl_result.scalars().all()
    approved_dicts = [
        {
            "change_type": c.change_type,
            "section": c.section,
            "original_text": c.original_text,
            "final_text": c.final_text or c.proposed_text,
            "reason": c.reason,
        }
        for c in approved
    ]

    # Get Anthropic key
    anthropic_key = await _get_anthropic_key(user, session)

    # Apply changes via Claude
    user_model = await get_user_model(user.id, session)
    from app.utils.usage_logger import set_usage_entity, get_session_usage
    set_usage_entity("domain_cv", domain_cv.id, None)
    final_cv_md = await apply_changes(
        master_cv_md=master.content_md,
        approved_changes=approved_dicts,
        country_rules=country_rules,
        user_anthropic_key=anthropic_key,
        model=user_model,
    )

    # Compute S3 vs master
    s3_result = await compute_s3_score(
        domain_cv_md=final_cv_md,
        master_cv_md=master.content_md,
        user_anthropic_key=anthropic_key,
        model=user_model,
    )
    s3_master = s3_result["s3_score"]

    # S3 vs domain (same score at generation time — it IS the domain CV)
    s3_domain = 100.0  # Domain CV is being created, no prior domain to compare against

    # Determine status based on S3 vs master
    if s3_master >= settings.s3_review_threshold:
        cv_status = CVStatus.active
    elif s3_master >= settings.s3_block_threshold:
        cv_status = CVStatus.review_required
    else:
        cv_status = CVStatus.blocked

    # Save to storage
    path = cv_domain_path(user.id, domain_cv.id, domain_cv.version)
    await save_text_file(final_cv_md, path)

    # Update domain CV record
    domain_cv.content_md = final_cv_md
    domain_cv.status = cv_status
    domain_cv.s3_domain = s3_domain
    domain_cv.s3_master = s3_master
    domain_cv.file_path = path

    await session.commit()
    await session.refresh(domain_cv)

    # V2: Auto-create feed profile for this domain CV
    if cv_status == CVStatus.active:
        try:
            from app.agents.feed_agents import create_feed_profile_for_domain_cv
            feed_result = await create_feed_profile_for_domain_cv(
                domain_cv_id=domain_cv.id,
                user_id=user.id,
                session=session,
                api_key=anthropic_key,
                model=settings.anthropic_model,
            )
            if feed_result:
                await session.commit()
                print(f"✅ Feed profile created: {feed_result['feed_name']}")
        except Exception as e:
            print(f"⚠️ Feed profile creation failed (non-blocking): {e}")

    # Hybrid-RAG: (re)compute the domain CV essence (best-effort) once it's active.
    if cv_status == CVStatus.active:
        await _compute_domain_essence(domain_cv, user, session)
        # Essence commit expired the object — reload before serialising (avoids MissingGreenlet 500).
        await session.refresh(domain_cv)

    _out = DomainCVRead.model_validate(domain_cv)
    _u = get_session_usage()
    _out.tokens_used = _u["tokens"] or None
    _out.cost_inr = round(_u["cost_inr"], 2) or None
    return _out


@router.post("/master/recompute-essence",
             dependencies=[Depends(require_active_subscription)])
async def recompute_master_essence(user: User = Depends(current_active_user),
                                   session: AsyncSession = Depends(get_db)):
    """Manually (re)compute the master CV essence."""
    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
    if not master:
        raise HTTPException(status_code=404, detail="No master CV found")
    ok = await _compute_master_essence(master, user, session)
    if not ok:
        raise HTTPException(status_code=502, detail="Essence extraction failed — check your Anthropic key")
    return {"computed": True, "keywords": len((master.essence_json or {}).get("keywords", []))}


@router.post("/domains/{domain_cv_id}/recompute-essence",
             dependencies=[Depends(require_active_subscription)])
async def recompute_domain_essence(domain_cv_id: uuid.UUID, user: User = Depends(current_active_user),
                                   session: AsyncSession = Depends(get_db)):
    """Manually (re)compute a domain CV essence."""
    dcv = (await session.execute(
        select(DomainCV).where(DomainCV.id == domain_cv_id, DomainCV.user_id == user.id))).scalar_one_or_none()
    if not dcv:
        raise HTTPException(status_code=404, detail="Domain CV not found")
    ok = await _compute_domain_essence(dcv, user, session)
    if not ok:
        raise HTTPException(status_code=502, detail="Essence extraction failed — apply the domain CV first")
    return {"computed": True, "keywords": len((dcv.essence_json or {}).get("keywords", []))}


@router.post("/domains/{domain_cv_id}/regenerate")
async def regenerate_domain_cv(
    domain_cv_id: uuid.UUID,
    response: Response,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Regenerate a stale domain CV.
    Auto-approves all changes (bulk regeneration after master CV update).
    """
    dcv_result = await session.execute(
        select(DomainCV).where(DomainCV.id == domain_cv_id, DomainCV.user_id == user.id)
    )
    domain_cv = dcv_result.scalar_one_or_none()
    if not domain_cv:
        raise HTTPException(status_code=404, detail="Domain CV not found")

    # Generate changelog (same as generate endpoint but auto-approve all)
    body = DomainCVCreate(
        industry_id=domain_cv.industry_id,
        function_id=domain_cv.function_id,
        country_code=domain_cv.country_code,
    )
    # Trigger generate + auto-approve + apply. KEYWORD args matching the signature
    # (body, response, user, session) — a positional call swapped session into `user`
    # → user.id AttributeError (500). Keywords prevent that recurring.
    await generate_domain_cv_changelog(body=body, response=response, user=user, session=session)

    # Bulk approve all
    await bulk_change_action(domain_cv_id, ChangeLogBulkAction(action="approve_all"), user, session)

    # Apply
    result = await apply_domain_cv_changes(domain_cv_id, user, session)
    return result


@router.get("/domains/{domain_cv_id}/versions", response_model=List[DomainCVVersionRead])
async def get_domain_cv_versions(
    domain_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Version history for a domain CV."""
    result = await session.execute(
        select(DomainCVVersion)
        .where(DomainCVVersion.domain_cv_id == domain_cv_id)
        .order_by(DomainCVVersion.version.desc())
    )
    return [DomainCVVersionRead.model_validate(v) for v in result.scalars().all()]


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_change(
    domain_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> ChangeLog:
    result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.id == change_id,
            ChangeLog.domain_cv_id == domain_cv_id,
            ChangeLog.user_id == user_id,
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")
    return change

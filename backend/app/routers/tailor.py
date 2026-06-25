"""
Tailor router — job-specific CV tailoring flow.

Flow:
1. POST /tailor/generate      → one Claude call: changelog + CL + email + S2
2. User reviews change log     → approve / reject / edit each change
3. POST /tailor/apply/{id}    → apply changes, compute S3, return final package
4. POST /tailor/send/{id}     → send application (Phase 7)
"""
import uuid
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import settings
from app.models.user import User, UserCredentials, UserPlan, UserPreferences
from app.models.job import Job, JobStatus, EmailThread, EmailDirection, EmailClassification
from app.models.cv import (
    MasterCV, DomainCV, TailoredCV, ChangeLog,
    CVStatus, ChangeType, ChangeStatus
)
from app.models.domain import CountryMaster
from app.auth.dependencies import current_active_user
from app.utils.subscription import require_active_subscription
from app.utils.encryption import decrypt_if_present
from app.utils.model import get_user_model
from app.agents.tailor_agents import (
    generate_tailor_package,
    apply_tailor_changes,
    regenerate_cover_letter,
    generate_followup_email,
    extract_jd_highlights,
)
from app.agents.cv_agents import compute_s3_score
from app.schemas.tailor import (
    TailorRequest, TailorPackageRead, TailorChangeRead,
    TailorApplyResult, RegenerateCLRequest, FollowUpRequest,
    ApplyMethodRequest,
)
from app.schemas.cv import ChangeLogItemRead, ChangeLogEdit, ChangeLogBulkAction

router = APIRouter()


async def _get_anthropic_key(user: User, session: AsyncSession) -> Optional[str]:
    if user.plan == UserPlan.default:
        result = await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id)
        )
        creds = result.scalar_one_or_none()
        if creds and creds.anthropic_api_key_enc:
            return decrypt_if_present(creds.anthropic_api_key_enc)
    return settings.platform_anthropic_api_key or settings.anthropic_api_key


def _get_s3_status(s3_master: float, s3_block: int, s3_review: int) -> str:
    if s3_master >= s3_review:
        return "green"
    elif s3_master >= s3_block:
        return "amber"
    return "blocked"


def _country_rule_display(country) -> list:
    """Human-readable 'country rules applied' list for the Tailor left panel.
    Each: {applied: bool, text: str} — applied=False renders as a removal (×)."""
    if not country:
        return []
    rules = []
    if not country.phone_on_cv:
        rules.append({"applied": False, "text": "Phone removed"})
    if country.remove_photo:
        rules.append({"applied": False, "text": "Photo line removed"})
    if country.remove_dob:
        rules.append({"applied": False, "text": "DOB removed"})
    if country.remove_marital_status:
        rules.append({"applied": False, "text": "Marital status removed"})
    if country.relocation_note:
        rules.append({"applied": True, "text": "Relocation note added"})
    if country.privacy_law:
        rules.append({"applied": True, "text": f"{country.privacy_law}-compliant format"})
    return rules


@router.post("/jd-highlights")
async def jd_highlights(
    body: TailorRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Cheap JD-only analysis for the Tailor page left panel:
    {matches, gaps} (Claude) + country_rules (derived from the domain CV's country)."""
    job = (await session.execute(
        select(Job).where(Job.id == body.job_id, Job.user_id == user.id)
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Country rules from the selected domain CV's country (if provided).
    country_rules = []
    if body.domain_cv_id:
        dcv = (await session.execute(
            select(DomainCV).where(DomainCV.id == body.domain_cv_id, DomainCV.user_id == user.id)
        )).scalar_one_or_none()
        if dcv:
            country = (await session.execute(
                select(CountryMaster).where(CountryMaster.country_code == dcv.country_code)
            )).scalar_one_or_none()
            country_rules = _country_rule_display(country)

    anthropic_key = await _get_anthropic_key(user, session)
    jd_text = job.jd_md or job.jd_raw or ""
    result = await extract_jd_highlights(
        jd_text, model=await get_user_model(user.id, session), user_anthropic_key=anthropic_key)
    return {"matches": result["matches"], "gaps": result["gaps"], "country_rules": country_rules}


# ══════════════════════════════════════════════════════════════
# STEP 1: GENERATE (tailor + CL + email + S2 in one call)
# ══════════════════════════════════════════════════════════════

@router.post("/generate", response_model=TailorPackageRead,
             dependencies=[Depends(require_active_subscription)])
async def generate_tailor(
    body: TailorRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Start the tailor flow. One Claude call returns:
    - Change log (bounded edits for this specific JD)
    - Cover letter draft
    - Email draft
    - S2 score

    Creates a TailoredCV record in 'pending' state.
    User then reviews the change log before hitting Apply.
    """
    # Load job
    job_result = await session.execute(
        select(Job).where(Job.id == body.job_id, Job.user_id == user.id)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.jd_raw and not job.jd_md:
        raise HTTPException(status_code=400, detail="Job has no JD content to tailor against")

    # Load domain CV
    dcv_result = await session.execute(
        select(DomainCV).where(DomainCV.id == body.domain_cv_id, DomainCV.user_id == user.id)
    )
    domain_cv = dcv_result.scalar_one_or_none()
    if not domain_cv:
        raise HTTPException(status_code=404, detail="Domain CV not found")
    if domain_cv.status == CVStatus.blocked:
        raise HTTPException(
            status_code=400,
            detail="Domain CV is blocked (S3 below threshold). Regenerate it first."
        )

    # Load master CV
    master_result = await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )
    master = master_result.scalar_one_or_none()
    if not master:
        raise HTTPException(status_code=400, detail="No master CV found")

    # Load country rules
    co_result = await session.execute(
        select(CountryMaster).where(CountryMaster.country_code == domain_cv.country_code)
    )
    country = co_result.scalar_one_or_none()
    country_rules = {
        "phone_on_cv": country.phone_on_cv if country else True,
        "relocation_note": country.relocation_note if country else None,
        "lines_to_add": country.lines_to_add if country else "[]",
    }

    # Load user preferences for CL settings
    prefs_result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    cl_tone = prefs.cl_tone if prefs else "professional"
    cl_template = prefs.cl_template if prefs else "random"

    anthropic_key = await _get_anthropic_key(user, session)
    user_model = await get_user_model(user.id, session)
    from app.utils.usage_logger import set_usage_entity, get_session_usage
    set_usage_entity("job", job.id, f"{job.company} · {job.role}")

    # CV template content rules → injected into the tailor system prompt (global + domain override)
    from app.models.cv_template import CVTemplate, DomainCVTemplateOverride
    from app.utils.cv_template import get_effective_template, build_content_rules_prompt
    gtpl = (await session.execute(
        select(CVTemplate).where(CVTemplate.user_id == user.id))).scalar_one_or_none()
    dovr = (await session.execute(select(DomainCVTemplateOverride).where(
        DomainCVTemplateOverride.domain_cv_id == domain_cv.id,
        DomainCVTemplateOverride.user_id == user.id))).scalar_one_or_none()
    content_rules = build_content_rules_prompt(get_effective_template(gtpl, dovr))

    # One batched Claude call
    jd_text = job.jd_md or job.jd_raw or ""
    package = await generate_tailor_package(
        domain_cv_md=domain_cv.content_md,
        master_cv_md=master.content_md,
        jd_text=jd_text,
        company=job.company,
        role=job.role,
        market=job.market or "EU",
        country_rules=country_rules,
        cl_tone=str(cl_tone),
        cl_template=str(cl_template),
        user_name=user.name or "Candidate",
        user_email=user.email,
        recruiter_email=job.recruiter_email,
        user_anthropic_key=anthropic_key,
        model=user_model,
        content_rules=content_rules,
    )

    # Determine which template was actually used
    cl_used = cl_template if cl_template != "random" else "story_led"
    if prefs:
        prefs.cl_last_template_used = cl_used

    # Create TailoredCV record (content_md empty until Apply)
    tailored = TailoredCV(
        user_id=user.id,
        job_id=job.id,
        domain_cv_id=domain_cv.id,
        cv_md="",  # filled after Apply
        cover_letter_md=package["cover_letter_md"],
        email_draft=package["email_draft"],
        s2=package["s2_score"],
        cl_template_used=cl_used,
    )
    session.add(tailored)
    await session.flush()

    # Link to job
    job.tailored_cv_id = tailored.id
    job.s2 = package["s2_score"]

    # Save change log items
    for change in package["changelog"]:
        cl_item = ChangeLog(
            user_id=user.id,
            tailored_cv_id=tailored.id,
            change_type=change.get("change_type", ChangeType.rephrase),
            section=change.get("section"),
            original_text=change.get("original_text"),
            proposed_text=change.get("proposed_text"),
            reason=change.get("reason"),
            status=ChangeStatus.pending,
        )
        session.add(cl_item)

    await session.commit()

    return TailorPackageRead(
        tailored_cv_id=tailored.id,
        s2_score=package["s2_score"],
        s2_key_matches=package["s2_key_matches"],
        changelog=package["changelog"],
        cover_letter_md=package["cover_letter_md"],
        email_draft=package["email_draft"],
        cl_template_used=cl_used,
        tokens_used=get_session_usage()["tokens"] or None,
        cost_inr=round(get_session_usage()["cost_inr"], 2) or None,
    )


# ══════════════════════════════════════════════════════════════
# CHANGE LOG MANAGEMENT
# ══════════════════════════════════════════════════════════════

@router.get("/{tailored_cv_id}/changelog", response_model=List[ChangeLogItemRead])
async def get_tailor_changelog(
    tailored_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.tailored_cv_id == tailored_cv_id,
            ChangeLog.user_id == user.id,
        ).order_by(ChangeLog.created_at)
    )
    return [ChangeLogItemRead.model_validate(c) for c in result.scalars().all()]


@router.post("/{tailored_cv_id}/changelog/{change_id}/approve")
async def approve_tailor_change(
    tailored_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    change = await _get_change(tailored_cv_id, change_id, user.id, session)
    change.status = ChangeStatus.approved
    change.final_text = change.proposed_text
    await session.commit()
    return {"status": "approved"}


@router.put("/{tailored_cv_id}/changelog/{change_id}/edit")
async def edit_tailor_change(
    tailored_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    body: ChangeLogEdit,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    change = await _get_change(tailored_cv_id, change_id, user.id, session)
    change.status = ChangeStatus.approved_edited
    change.final_text = body.final_text
    await session.commit()
    return {"status": "approved_edited", "final_text": body.final_text}


@router.post("/{tailored_cv_id}/changelog/{change_id}/reject")
async def reject_tailor_change(
    tailored_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    change = await _get_change(tailored_cv_id, change_id, user.id, session)
    change.status = ChangeStatus.rejected
    await session.commit()
    return {"status": "rejected"}


@router.post("/{tailored_cv_id}/changelog/bulk")
async def bulk_tailor_action(
    tailored_cv_id: uuid.UUID,
    body: ChangeLogBulkAction,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if body.action not in ("approve_all", "reject_all"):
        raise HTTPException(status_code=400, detail="Invalid action")

    result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.tailored_cv_id == tailored_cv_id,
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
    return {"updated": len(changes)}


# ══════════════════════════════════════════════════════════════
# STEP 2: APPLY (after change log approved, compute S3)
# ══════════════════════════════════════════════════════════════

@router.post("/{tailored_cv_id}/apply", response_model=TailorApplyResult,
             dependencies=[Depends(require_active_subscription)])
async def apply_tailor(
    tailored_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Apply approved changes, compute S3 vs domain and vs master.
    This is triggered by the Generate button in the UI.

    S3 rules:
    >= 90% → green (safe to send)
    85-89% → amber (review before send)
    < 85%  → blocked
    """
    # Load tailored CV
    tcv_result = await session.execute(
        select(TailoredCV).where(
            TailoredCV.id == tailored_cv_id,
            TailoredCV.user_id == user.id,
        )
    )
    tailored = tcv_result.scalar_one_or_none()
    if not tailored:
        raise HTTPException(status_code=404, detail="Tailored CV not found")

    # Load domain CV
    dcv_result = await session.execute(
        select(DomainCV).where(DomainCV.id == tailored.domain_cv_id)
    )
    domain_cv = dcv_result.scalar_one_or_none()

    # Load master CV
    master_result = await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )
    master = master_result.scalar_one_or_none()

    # Load country rules
    country_rules = {"phone_on_cv": True, "relocation_note": None}
    if domain_cv:
        co_result = await session.execute(
            select(CountryMaster).where(CountryMaster.country_code == domain_cv.country_code)
        )
        country = co_result.scalar_one_or_none()
        if country:
            country_rules = {
                "phone_on_cv": country.phone_on_cv,
                "relocation_note": country.relocation_note,
            }

    # Load approved changes
    cl_result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.tailored_cv_id == tailored_cv_id,
            ChangeLog.status.in_([ChangeStatus.approved, ChangeStatus.approved_edited]),
        )
    )
    approved = cl_result.scalars().all()
    approved_dicts = [
        {
            "change_type": str(c.change_type),
            "section": c.section,
            "original_text": c.original_text,
            "final_text": c.final_text or c.proposed_text,
            "reason": c.reason,
        }
        for c in approved
    ]

    anthropic_key = await _get_anthropic_key(user, session)
    user_model = await get_user_model(user.id, session)
    from app.utils.usage_logger import set_usage_entity, get_session_usage
    set_usage_entity("job", tailored.job_id, None)

    # Apply changes
    base_cv = domain_cv.content_md if domain_cv else master.content_md if master else ""
    final_cv_md = await apply_tailor_changes(
        domain_cv_md=base_cv,
        approved_changes=approved_dicts,
        country_rules=country_rules,
        user_anthropic_key=anthropic_key,
        model=user_model,
    )

    # Compute S3 vs domain CV
    if domain_cv and domain_cv.content_md:
        s3_domain_result = await compute_s3_score(
            domain_cv_md=final_cv_md,
            master_cv_md=domain_cv.content_md,
            user_anthropic_key=anthropic_key,
            model=user_model,
        )
        s3_domain = s3_domain_result["s3_score"]
    else:
        s3_domain = 100.0

    # Compute S3 vs master CV (the gate)
    s3_flags: list = []
    if master:
        s3_master_result = await compute_s3_score(
            domain_cv_md=final_cv_md,
            master_cv_md=master.content_md,
            user_anthropic_key=anthropic_key,
            model=user_model,
        )
        s3_master = s3_master_result["s3_score"]
        s3_flags = s3_master_result.get("flags", [])
    else:
        s3_master = s3_domain

    s3_status = _get_s3_status(
        s3_master,
        settings.s3_block_threshold,
        settings.s3_review_threshold,
    )

    # Save to tailored CV record
    tailored.cv_md = final_cv_md
    tailored.s2 = tailored.s2  # already set from generate step
    tailored.s3_domain = s3_domain
    tailored.s3_master = s3_master

    # Update job scores
    job_result = await session.execute(
        select(Job).where(Job.id == tailored.job_id)
    )
    job = job_result.scalar_one_or_none()
    if job:
        job.s3_domain = s3_domain
        job.s3_master = s3_master

    await session.commit()

    # This apply's tokens + the job's full tailoring session total (generate + apply).
    this_usage = get_session_usage()
    from app.models.usage import APIUsageLog
    job_rows = (await session.execute(
        select(APIUsageLog).where(
            APIUsageLog.user_id == user.id, APIUsageLog.provider == "anthropic",
            APIUsageLog.entity_id == str(tailored.job_id))
    )).scalars().all()
    sess_tokens = sum(r.total_tokens or 0 for r in job_rows)
    sess_inr = round(sum(r.estimated_cost_inr or 0 for r in job_rows), 2)

    # Page-budget overflow check vs the user's CV template (global + domain override)
    from app.models.cv_template import CVTemplate, DomainCVTemplateOverride
    from app.utils.cv_template import get_effective_template, check_overflow
    gtpl = (await session.execute(
        select(CVTemplate).where(CVTemplate.user_id == user.id))).scalar_one_or_none()
    dovr = None
    if tailored.domain_cv_id:
        dovr = (await session.execute(select(DomainCVTemplateOverride).where(
            DomainCVTemplateOverride.domain_cv_id == tailored.domain_cv_id,
            DomainCVTemplateOverride.user_id == user.id))).scalar_one_or_none()
    overflow = check_overflow(final_cv_md, get_effective_template(gtpl, dovr))

    return TailorApplyResult(
        tailored_cv_id=tailored.id,
        tailored_cv_md=final_cv_md,
        cover_letter_md=tailored.cover_letter_md or "",
        email_draft=tailored.email_draft or "",
        s2_score=tailored.s2 or 0,
        s3_domain=s3_domain,
        s3_master=s3_master,
        s3_status=s3_status,
        s3_flags=s3_flags,
        cl_template_used=tailored.cl_template_used or "",
        tokens_used=this_usage["tokens"] or None,
        cost_inr=round(this_usage["cost_inr"], 2) or None,
        session_tokens=sess_tokens or None,
        session_cost_inr=sess_inr or None,
        overflow=overflow,
    )


# ══════════════════════════════════════════════════════════════
# TRIM TO FIT  (remove lowest-impact approved changes until within page budget)
# ══════════════════════════════════════════════════════════════

# Removal order — least content impact first. DESELECT is never removed (it shrinks the CV).
_TRIM_PRIORITY = ["reorder", "keyword_injection", "rephrase"]


@router.post("/{tailored_cv_id}/trim")
async def trim_tailored_cv(
    tailored_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Remove the lowest-impact approved changes (reorder → keyword_injection → rephrase;
    never deselect) and re-apply until the CV fits the template's word budget.
    Returns {trimmed_cv_md, removed_changes, word_count, max_words, fits}."""
    from app.utils.cv_template import count_words, get_effective_template
    from app.models.cv_template import CVTemplate, DomainCVTemplateOverride

    tailored = (await session.execute(select(TailoredCV).where(
        TailoredCV.id == tailored_cv_id, TailoredCV.user_id == user.id))).scalar_one_or_none()
    if not tailored or not tailored.cv_md:
        raise HTTPException(status_code=404, detail="Apply the tailored CV first")

    domain_cv = (await session.execute(
        select(DomainCV).where(DomainCV.id == tailored.domain_cv_id))).scalar_one_or_none() if tailored.domain_cv_id else None
    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
    base_cv = (domain_cv.content_md if domain_cv else None) or (master.content_md if master else "")

    # Effective word budget
    gtpl = (await session.execute(
        select(CVTemplate).where(CVTemplate.user_id == user.id))).scalar_one_or_none()
    dovr = None
    if tailored.domain_cv_id:
        dovr = (await session.execute(select(DomainCVTemplateOverride).where(
            DomainCVTemplateOverride.domain_cv_id == tailored.domain_cv_id,
            DomainCVTemplateOverride.user_id == user.id))).scalar_one_or_none()
    max_words = get_effective_template(gtpl, dovr)["max_words"]

    approved = (await session.execute(select(ChangeLog).where(
        ChangeLog.tailored_cv_id == tailored_cv_id,
        ChangeLog.status.in_([ChangeStatus.approved, ChangeStatus.approved_edited])))).scalars().all()

    def _ct(c):
        return c.change_type.value if hasattr(c.change_type, "value") else str(c.change_type)

    anthropic_key = await _get_anthropic_key(user, session)
    user_model = await get_user_model(user.id, session)

    current_md = tailored.cv_md
    removed = []
    kept = list(approved)

    for ctype in _TRIM_PRIORITY:
        if count_words(current_md) <= max_words:
            break
        batch = [c for c in kept if _ct(c) == ctype]
        if not batch:
            continue
        for c in batch:
            c.status = ChangeStatus.rejected
            removed.append({"change_type": ctype, "section": c.section,
                            "text": c.final_text or c.proposed_text or c.original_text})
        kept = [c for c in kept if _ct(c) != ctype]
        kept_dicts = [{"change_type": _ct(c), "section": c.section, "original_text": c.original_text,
                       "final_text": c.final_text or c.proposed_text, "reason": c.reason} for c in kept]
        current_md = await apply_tailor_changes(
            domain_cv_md=base_cv, approved_changes=kept_dicts, country_rules={},
            user_anthropic_key=anthropic_key, model=user_model)

    tailored.cv_md = current_md
    await session.commit()
    wc = count_words(current_md)
    return {"trimmed_cv_md": current_md, "removed_changes": removed,
            "word_count": wc, "max_words": max_words, "fits": wc <= max_words}


# ══════════════════════════════════════════════════════════════
# COVER LETTER REGENERATION
# ══════════════════════════════════════════════════════════════

@router.post("/{tailored_cv_id}/regenerate-cl")
async def regenerate_cl(
    tailored_cv_id: uuid.UUID,
    body: RegenerateCLRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Regenerate cover letter with a different template."""
    tcv_result = await session.execute(
        select(TailoredCV).where(
            TailoredCV.id == tailored_cv_id,
            TailoredCV.user_id == user.id,
        )
    )
    tailored = tcv_result.scalar_one_or_none()
    if not tailored:
        raise HTTPException(status_code=404, detail="Tailored CV not found")

    job_result = await session.execute(select(Job).where(Job.id == tailored.job_id))
    job = job_result.scalar_one_or_none()

    prefs_result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    cl_tone = str(prefs.cl_tone) if prefs else "professional"

    anthropic_key = await _get_anthropic_key(user, session)
    user_model = await get_user_model(user.id, session)
    new_cl, template_used = await regenerate_cover_letter(
        tailored_cv_md=tailored.cv_md or "",
        jd_text=job.jd_md or job.jd_raw or "" if job else "",
        company=job.company if job else "Company",
        role=job.role if job else "Role",
        user_name=user.name or "Candidate",
        cl_tone=cl_tone,
        cl_template="random",
        exclude_template=body.exclude_template,
        user_anthropic_key=anthropic_key,
        model=user_model,
    )

    tailored.cover_letter_md = new_cl
    tailored.cl_template_used = template_used
    await session.commit()

    from app.utils.usage_logger import get_session_usage
    _u = get_session_usage()
    return {"cover_letter_md": new_cl, "template_used": template_used,
            "tokens_used": _u["tokens"] or None, "cost_inr": round(_u["cost_inr"], 2) or None}


# ══════════════════════════════════════════════════════════════
# FOLLOW-UP EMAIL
# ══════════════════════════════════════════════════════════════

@router.post("/followup/{job_id}")
async def draft_followup(
    job_id: uuid.UUID,
    body: FollowUpRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Draft a follow-up email for an applied job."""
    job_result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    applied_str = job.applied_at.strftime("%B %d, %Y") if job.applied_at else "recently"
    anthropic_key = await _get_anthropic_key(user, session)
    user_model = await get_user_model(user.id, session)

    email = await generate_followup_email(
        company=job.company,
        role=job.role,
        applied_at=applied_str,
        user_name=user.name or "Candidate",
        context=body.context,
        user_anthropic_key=anthropic_key,
        model=user_model,
    )
    return {"email_draft": email}


# ── Internal helper ───────────────────────────────────────────────────────────

async def _get_change(
    tailored_cv_id: uuid.UUID,
    change_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> ChangeLog:
    result = await session.execute(
        select(ChangeLog).where(
            ChangeLog.id == change_id,
            ChangeLog.tailored_cv_id == tailored_cv_id,
            ChangeLog.user_id == user_id,
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")
    return change

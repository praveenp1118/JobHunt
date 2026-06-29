"""
PDF router — generate and serve CV / cover letter PDFs on demand.
PDFs are generated fresh each time (not cached) to always reflect latest content.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User, UserCredentials
from app.models.cv import MasterCV, DomainCV, TailoredCV
from app.models.job import Job
from app.auth.dependencies import current_active_user
from app.utils.pdf_generator import cv_md_to_pdf, cl_md_to_pdf, make_filename

router = APIRouter()


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ── Master CV ─────────────────────────────────────────────────────────────────

async def _user_pdf_styles(session, user_id, domain_cv_id=None) -> dict:
    """Build PDF styles from the user's CV template (+ optional domain override)."""
    from app.models.cv_template import CVTemplate, DomainCVTemplateOverride
    from app.utils.cv_template import get_effective_template, build_pdf_styles
    gtpl = (await session.execute(
        select(CVTemplate).where(CVTemplate.user_id == user_id))).scalar_one_or_none()
    dovr = None
    if domain_cv_id:
        dovr = (await session.execute(select(DomainCVTemplateOverride).where(
            DomainCVTemplateOverride.domain_cv_id == domain_cv_id,
            DomainCVTemplateOverride.user_id == user_id))).scalar_one_or_none()
    return build_pdf_styles(get_effective_template(gtpl, dovr))


@router.get("/master-cv")
async def download_master_cv_pdf(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Download current master CV as PDF."""
    result = await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )
    cv = result.scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="No master CV found")

    pdf = await cv_md_to_pdf(cv.content_md, await _user_pdf_styles(session, user.id))
    name = (user.name or "CV").replace(" ", "_")
    return _pdf_response(pdf, f"CV_{name}_Master.pdf")


# ── Domain CV ─────────────────────────────────────────────────────────────────

@router.get("/domain-cv/{domain_cv_id}")
async def download_domain_cv_pdf(
    domain_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Download a domain CV as PDF."""
    result = await session.execute(
        select(DomainCV).where(DomainCV.id == domain_cv_id, DomainCV.user_id == user.id)
    )
    cv = result.scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="Domain CV not found")
    if not cv.content_md:
        raise HTTPException(status_code=400, detail="Domain CV has no content — apply changes first")

    pdf = await cv_md_to_pdf(cv.content_md, await _user_pdf_styles(session, user.id, domain_cv_id))
    name = (user.name or "CV").replace(" ", "_")
    return _pdf_response(pdf, f"CV_{name}_Domain_v{cv.version}.pdf")


# ── Tailored CV ───────────────────────────────────────────────────────────────

@router.get("/tailored-cv/{tailored_cv_id}")
async def download_tailored_cv_pdf(
    tailored_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Download a tailored CV as PDF."""
    result = await session.execute(
        select(TailoredCV).where(TailoredCV.id == tailored_cv_id, TailoredCV.user_id == user.id)
    )
    tailored = result.scalar_one_or_none()
    if not tailored:
        raise HTTPException(status_code=404, detail="Tailored CV not found")
    if not tailored.cv_md:
        raise HTTPException(status_code=400, detail="Tailored CV not generated yet — click Apply first")

    pdf = await cv_md_to_pdf(tailored.cv_md, await _user_pdf_styles(session, user.id, tailored.domain_cv_id))

    # Save to the user-scoped tailored folder (folder auto-created on first write).
    from app.utils.storage import tailored_pdf_path, pdf_storage_name, save_binary_file
    job = (await session.execute(select(Job).where(Job.id == tailored.job_id))).scalar_one_or_none()
    fname = pdf_storage_name(user.id, tailored.job_id, job.company if job else "", "cv")
    path = tailored_pdf_path(user.id, fname)
    await save_binary_file(pdf, path)
    tailored.cv_pdf_path = path
    await session.commit()

    return _pdf_response(pdf, make_filename(user.name, "CV"))


# ── Cover Letter ──────────────────────────────────────────────────────────────

@router.get("/cover-letter/{tailored_cv_id}")
async def download_cover_letter_pdf(
    tailored_cv_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Download a cover letter as PDF."""
    result = await session.execute(
        select(TailoredCV).where(TailoredCV.id == tailored_cv_id, TailoredCV.user_id == user.id)
    )
    tailored = result.scalar_one_or_none()
    if not tailored:
        raise HTTPException(status_code=404, detail="Tailored CV not found")
    if not tailored.cover_letter_md:
        raise HTTPException(status_code=400, detail="No cover letter generated")

    # Get user contact info
    creds_result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = creds_result.scalar_one_or_none()
    contact = creds.gmail_address if creds else user.email

    pdf = await cl_md_to_pdf(
        tailored.cover_letter_md,
        user_name=user.name or "Candidate",
        user_contact=contact or "",
    )

    # Save to the user-scoped cover_letters folder (folder auto-created on first write).
    from app.utils.storage import cover_letter_pdf_path, pdf_storage_name, save_binary_file
    job = (await session.execute(select(Job).where(Job.id == tailored.job_id))).scalar_one_or_none()
    fname = pdf_storage_name(user.id, tailored.job_id, job.company if job else "", "cl")
    path = cover_letter_pdf_path(user.id, fname)
    await save_binary_file(pdf, path)
    tailored.cl_pdf_path = path
    await session.commit()

    return _pdf_response(pdf, make_filename(user.name, "CoverLetter"))

"""CV Template endpoints — global template + per-domain overrides."""
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.cv_template import CVTemplate, DomainCVTemplateOverride
from app.auth.dependencies import current_active_user
from app.utils.cv_template import FONTS, compute_max_words

router = APIRouter()


def _serialize(t: CVTemplate) -> dict:
    return {
        "font_family": t.font_family, "font_size": t.font_size,
        "heading_font_family": t.heading_font_family, "heading_font_size": t.heading_font_size,
        "heading_bold": t.heading_bold, "margin_size": t.margin_size,
        "line_spacing": t.line_spacing, "bullet_style": t.bullet_style, "accent_color": t.accent_color,
        "max_pages": t.max_pages, "overflow_action": t.overflow_action,
        "never_modify_sections": t.never_modify_sections, "section_order": t.section_order,
        "max_words": t.max_words,
    }


async def _get_or_create(session, user_id) -> CVTemplate:
    t = (await session.execute(
        select(CVTemplate).where(CVTemplate.user_id == user_id))).scalar_one_or_none()
    if not t:
        t = CVTemplate(user_id=user_id)
        session.add(t)
        await session.commit()
        await session.refresh(t)
    return t


class CVTemplateUpdate(BaseModel):
    font_family: Optional[str] = None
    font_size: Optional[int] = None
    heading_font_family: Optional[str] = None
    heading_font_size: Optional[int] = None
    heading_bold: Optional[bool] = None
    margin_size: Optional[str] = None
    line_spacing: Optional[float] = None
    bullet_style: Optional[str] = None
    accent_color: Optional[str] = None
    max_pages: Optional[int] = None
    overflow_action: Optional[str] = None
    never_modify_sections: Optional[List[str]] = None
    section_order: Optional[List[str]] = None


@router.get("/cv")
async def get_cv_template(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    return _serialize(await _get_or_create(session, user.id))


@router.put("/cv")
async def update_cv_template(body: CVTemplateUpdate, user: User = Depends(current_active_user),
                            session: AsyncSession = Depends(get_db)):
    t = await _get_or_create(session, user.id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(t, k, v)
    # max_words is always derived from max_pages (never set directly).
    if "max_pages" in data and data["max_pages"]:
        t.max_words = compute_max_words(data["max_pages"])
    await session.commit()
    await session.refresh(t)
    return _serialize(t)


@router.get("/cv/fonts")
async def get_fonts(user: User = Depends(current_active_user)):
    return {"fonts": FONTS}


# ── Domain overrides ──

def _serialize_override(o: DomainCVTemplateOverride) -> dict:
    return {
        "domain_cv_id": str(o.domain_cv_id),
        "font_family": o.font_family, "font_size": o.font_size, "max_pages": o.max_pages,
        "overflow_action": o.overflow_action, "never_modify_sections": o.never_modify_sections,
        "section_order": o.section_order, "max_words": o.max_words,
    }


class DomainTemplateOverride(BaseModel):
    font_family: Optional[str] = None
    font_size: Optional[int] = None
    max_pages: Optional[int] = None
    overflow_action: Optional[str] = None
    never_modify_sections: Optional[List[str]] = None
    section_order: Optional[List[str]] = None


@router.get("/domain/{domain_cv_id}")
async def get_domain_override(domain_cv_id: uuid.UUID, user: User = Depends(current_active_user),
                              session: AsyncSession = Depends(get_db)):
    o = (await session.execute(select(DomainCVTemplateOverride).where(
        DomainCVTemplateOverride.domain_cv_id == domain_cv_id,
        DomainCVTemplateOverride.user_id == user.id))).scalar_one_or_none()
    return {"override": _serialize_override(o) if o else None}


@router.put("/domain/{domain_cv_id}")
async def put_domain_override(domain_cv_id: uuid.UUID, body: DomainTemplateOverride,
                              user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    o = (await session.execute(select(DomainCVTemplateOverride).where(
        DomainCVTemplateOverride.domain_cv_id == domain_cv_id,
        DomainCVTemplateOverride.user_id == user.id))).scalar_one_or_none()
    if not o:
        o = DomainCVTemplateOverride(user_id=user.id, domain_cv_id=domain_cv_id)
        session.add(o)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(o, k, v)
    if "max_pages" in data and data["max_pages"]:
        o.max_words = compute_max_words(data["max_pages"])
    elif "max_pages" in data and not data["max_pages"]:
        o.max_words = None  # cleared → fall back to global
    await session.commit()
    await session.refresh(o)
    return {"override": _serialize_override(o)}


@router.delete("/domain/{domain_cv_id}")
async def delete_domain_override(domain_cv_id: uuid.UUID, user: User = Depends(current_active_user),
                                 session: AsyncSession = Depends(get_db)):
    o = (await session.execute(select(DomainCVTemplateOverride).where(
        DomainCVTemplateOverride.domain_cv_id == domain_cv_id,
        DomainCVTemplateOverride.user_id == user.id))).scalar_one_or_none()
    if o:
        await session.delete(o)
        await session.commit()
    return {"deleted": True}

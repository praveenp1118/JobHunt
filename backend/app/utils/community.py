"""
Community Insights — anonymised aggregation of job-search data across users.

NEVER stores CV content or PII. Only scores, JD highlights (derived from approved
keyword injections), and tailoring patterns. Insights surface only when ≥ 2
contributors exist (privacy floor).
"""
import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

APPROVED_STATUSES = {"approved", "approved_edited"}
MIN_CONTRIBUTORS = 2


def normalize_role(role: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.
    "Head of Product - AI" -> "head of product ai"."""
    if not role:
        return ""
    s = re.sub(r"[^\w\s]", " ", role.lower())
    return re.sub(r"\s+", " ", s).strip()


def normalize_company(company: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — so "Adyen", "adyen" and
    "Adyen, Inc." collapse to one community bucket. "ADYEN" -> "adyen"."""
    if not company:
        return ""
    s = re.sub(r"[^\w\s]", " ", company.lower())
    return re.sub(r"\s+", " ", s).strip()


def _enum(v):
    return v.value if hasattr(v, "value") else (str(v) if v is not None else None)


async def _domain_cv_label(session: AsyncSession, domain_cv_id) -> Optional[str]:
    if not domain_cv_id:
        return None
    from app.models.cv import DomainCV
    from app.models.domain import IndustryVertical
    row = (await session.execute(
        select(IndustryVertical.label, DomainCV.country_code)
        .select_from(DomainCV)
        .outerjoin(IndustryVertical, IndustryVertical.id == DomainCV.industry_id)
        .where(DomainCV.id == domain_cv_id)
    )).first()
    if not row:
        return None
    ind, cc = row
    return f"{ind or 'Domain'} × {cc or '—'}"


async def upsert_community_insights(session, user_id, job, tailored_cv, changelog) -> Optional[uuid.UUID]:
    """Merge one user's anonymised data into the shared insight for this company+role.
    Idempotent per (user, job). Returns the insight id (or None if not enough data)."""
    from app.models.community import CommunityJobInsight, CommunityContribution

    company = normalize_company(job.company or "")
    role_norm = normalize_role(job.role or "")
    if not company or not role_norm:
        return None

    # Idempotent: one contribution per (user, job).
    existing = (await session.execute(select(CommunityContribution).where(
        CommunityContribution.user_id == user_id, CommunityContribution.job_id == job.id))).scalar_one_or_none()
    if existing:
        return existing.insight_id

    # Find (jd_hash, then company+role) or create the insight row.
    insight = None
    if job.jd_hash:
        insight = (await session.execute(select(CommunityJobInsight).where(
            CommunityJobInsight.jd_hash == job.jd_hash))).scalars().first()
    if not insight:
        insight = (await session.execute(select(CommunityJobInsight).where(
            CommunityJobInsight.company == company,
            CommunityJobInsight.role_normalized == role_norm))).scalars().first()
    if not insight:
        insight = CommunityJobInsight(
            company=company, role_normalized=role_norm, market=job.market, jd_hash=job.jd_hash,
            contributor_count=0, jd_highlights=[], keyword_patterns=[], tailoring_patterns=[])
        session.add(insight)
        await session.flush()

    n = insight.contributor_count

    def _avg(old, new):
        if new is None:
            return old
        return round(float(new) if old is None else (old * n + float(new)) / (n + 1), 1)

    insight.avg_s1 = _avg(insight.avg_s1, job.s1)
    insight.avg_s1d = _avg(insight.avg_s1d, job.s1d)

    label = await _domain_cv_label(session, job.best_domain_cv_id or (tailored_cv.domain_cv_id if tailored_cv else None))
    if label:
        insight.best_domain_cv_label = label

    # Merge changelog-derived patterns (dicts keyed for in-place accumulation).
    tp = {p["change_type"]: dict(p) for p in (insight.tailoring_patterns or [])}
    kp = {p["keyword"]: dict(p) for p in (insight.keyword_patterns or [])}
    hl = {h["text"]: dict(h) for h in (insight.jd_highlights or [])}
    for c in (changelog or []):
        ct = _enum(c.change_type)
        entry = tp.setdefault(ct, {"change_type": ct, "approval_count": 0, "total_count": 0})
        entry["total_count"] += 1
        approved = _enum(c.status) in APPROVED_STATUSES
        if approved:
            entry["approval_count"] += 1
        if ct == "keyword_injection":
            kw = (c.proposed_text or c.final_text or c.original_text or "").strip()[:80]
            if kw:
                k = kp.setdefault(kw, {"keyword": kw, "injection_count": 0, "_approved": 0, "approval_rate": 0.0})
                k["injection_count"] += 1
                if approved:
                    k["_approved"] += 1
                k["approval_rate"] = round(k["_approved"] / k["injection_count"], 2)
                if approved:
                    h = hl.setdefault(kw, {"text": kw, "votes": 0, "category": "keyword"})
                    h["votes"] += 1
    insight.tailoring_patterns = list(tp.values())
    insight.keyword_patterns = list(kp.values())
    insight.jd_highlights = list(hl.values())
    insight.contributor_count = n + 1

    session.add(CommunityContribution(
        user_id=user_id, job_id=job.id, insight_id=insight.id,
        contributed_scores=(job.s1 is not None or job.s1d is not None),
        contributed_highlights=bool(insight.jd_highlights),
        contributed_tailoring=bool(changelog),
        is_anonymous=True))
    await session.flush()
    return insight.id


async def maybe_share_on_apply(session, user, job) -> Optional[uuid.UUID]:
    """If the user opted in (community_sharing_enabled) and the job has a tailored CV,
    contribute its anonymised insights. Fire-and-forget — never raises/blocks the apply."""
    try:
        from app.models.user import UserPreferences
        from app.models.cv import TailoredCV, ChangeLog
        prefs = (await session.execute(select(UserPreferences).where(
            UserPreferences.user_id == user.id))).scalar_one_or_none()
        if not prefs or not prefs.community_sharing_enabled:
            return None
        if not job.tailored_cv_id:
            return None
        tcv = (await session.execute(select(TailoredCV).where(
            TailoredCV.id == job.tailored_cv_id))).scalar_one_or_none()
        changelog = (await session.execute(select(ChangeLog).where(
            ChangeLog.tailored_cv_id == job.tailored_cv_id))).scalars().all()
        insight_id = await upsert_community_insights(session, user.id, job, tcv, list(changelog))
        await session.commit()
        if insight_id:
            print(f"🤝 Community insights shared for {job.company}")
        return insight_id
    except Exception as e:
        print(f"⚠️ community share failed: {e}")
        return None


async def get_community_insights(session, company, role, market=None, jd_hash=None) -> Optional[dict]:
    """Return aggregated insights only if ≥ MIN_CONTRIBUTORS, else None (privacy)."""
    from app.models.community import CommunityJobInsight

    company = normalize_company(company or "")
    role_norm = normalize_role(role or "")
    insight = None
    if jd_hash:
        insight = (await session.execute(select(CommunityJobInsight).where(
            CommunityJobInsight.jd_hash == jd_hash))).scalars().first()
    if not insight and company and role_norm:
        insight = (await session.execute(select(CommunityJobInsight).where(
            CommunityJobInsight.company == company,
            CommunityJobInsight.role_normalized == role_norm))).scalars().first()
    if not insight or insight.contributor_count < MIN_CONTRIBUTORS:
        return None

    kp = [{k: v for k, v in p.items() if k != "_approved"} for p in (insight.keyword_patterns or [])]
    return {
        "available": True,
        "contributor_count": insight.contributor_count,
        "avg_s1": insight.avg_s1,
        "avg_s1d": insight.avg_s1d,
        "best_domain_cv_label": insight.best_domain_cv_label,
        "jd_highlights": insight.jd_highlights or [],
        "keyword_patterns": kp,
        "tailoring_patterns": insight.tailoring_patterns or [],
    }

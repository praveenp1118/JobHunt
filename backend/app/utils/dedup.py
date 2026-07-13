"""Cross-source canonical dedup key + conflict-safe insert.

The same posting found by Apify, Bright Data, RSS or Gmail must collapse to ONE row.
build_dedup_key gives a tiered identity: canonical job-id → canonical URL → normalized
company+role+location (NOT description — description is what varies most across sources).

upsert_job inserts with ON CONFLICT (user_id, dedup_key) DO NOTHING, so parallel sources
can't race a duplicate in (the old SELECT-then-INSERT had a TOCTOU gap). Phase 1 is
DO NOTHING; DO-UPDATE-enrich (fill a partial row from a fuller later source — the
Bright-Data collect-by-URL payoff) is the flagged fast-follow.
"""
import hashlib
import re
from typing import Optional, Tuple
from urllib.parse import urlsplit

from sqlalchemy import select, and_, or_, case, func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.utils.community import normalize_company, normalize_role  # reuse existing

_LINKEDIN_ID = re.compile(r"/jobs/view/(\d+)")      # matches /comm/jobs/view/<id> too
_INDEED_JK = re.compile(r"[?&]jk=([0-9a-fA-F]+)")


def normalize_location(loc: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace (same shape as normalize_company)."""
    if not loc:
        return ""
    s = re.sub(r"[^\w\s]", " ", loc.lower())
    return re.sub(r"\s+", " ", s).strip()


def _canonical_job_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    u = url.lower()
    if "linkedin.com" in u:
        m = _LINKEDIN_ID.search(url)
        if m:
            return f"linkedin:{m.group(1)}"
    if "indeed." in u:
        m = _INDEED_JK.search(url)
        if m:
            return f"indeed:{m.group(1).lower()}"
    return None


def _canonical_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        p = urlsplit(url)
    except Exception:
        return None
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "").replace("/comm/", "/").rstrip("/")   # LinkedIn email form → canonical
    if not host and not path:
        return None
    return f"{host}{path}"   # tracking query dropped


_MAXLEN = 480   # keep well under the dedup_key column's varchar(512)


def _bounded(key: str) -> str:
    """Keep short keys human-readable; deterministically hash any that would overflow the
    column (tier-3 can reach ~765 chars from three String(255) fields; long URL paths too).
    Same input → same hash, so cross-source dedup still holds."""
    if len(key) <= _MAXLEN:
        return key
    return key[:64] + ":sha256:" + hashlib.sha256(key.encode()).hexdigest()


def build_dedup_key(company: Optional[str], role: Optional[str],
                    location: Optional[str], portal_url: Optional[str] = None) -> str:
    """Tiered cross-source identity. Always returns a non-empty string, ≤ 512 chars."""
    jid = _canonical_job_id(portal_url)
    if jid:
        return jid                                    # tier 1: linkedin:<id> / indeed:<jk> (short)
    cu = _canonical_url(portal_url)
    if cu:
        return _bounded(f"url:{cu}")                  # tier 2: canonical URL
    return _bounded("crl:" + "|".join([               # tier 3: company+role+location
        normalize_company(company or ""), normalize_role(role or ""), normalize_location(location or "")]))


async def upsert_job(session, values: dict) -> Tuple[object, bool]:
    """INSERT a job with ON CONFLICT (user_id, dedup_key) DO UPDATE that ENRICHES the
    existing row — fills gaps only, never overwrites good data, never touches user progress.

    Returns (job, created). created=False means the row already existed (whether or not it
    was enriched). Core insert applies the model's Python defaults (id/status/jd_language/…)
    and the DB server_default (created_at/updated_at) for any column not in `values`.

    Enrichment (raw job data ONLY):
      • jd_raw/jd_md/has_partial_jd → replaced ONLY when existing is PARTIAL and incoming is
        a genuinely FULL JD (≥100 chars). Never downgrades a full row back to partial.
      • portal_url / salary_range_raw / market → filled only when the existing value is NULL
        (coalesce; never overwrites a non-null existing value).
    PROTECTED (never in SET, so untouched on conflict): status, tailored_cv_id, all scores
      (s1/s1d/s2/s3_*/ats_*/pursuit_*/score_components/domain_cv_scores/best_domain_cv_id),
      notes, needs_hitl, scoring_status, source, source_feed_id/source_email_id, jd_hash,
      jd_highlights_json, company/role/location, recruiter_email, salary_expectation/offered,
      all interview/offer/follow-up/ghost fields, applied_at, created_at, s1_tokens/s1_cost_inr.

    NOTE: requires the UNIQUE (user_id, dedup_key) index (migration v7_dedup_key_unique)."""
    from app.models.job import Job
    values = dict(values)
    if not values.get("dedup_key"):
        values["dedup_key"] = build_dedup_key(
            values.get("company"), values.get("role"),
            values.get("location"), values.get("portal_url"))

    ins = pg_insert(Job).values(**values)
    ex = ins.excluded
    # "existing is partial, incoming is a genuinely full JD" — the only enrichment trigger.
    enrich_full = and_(
        Job.has_partial_jd == True,                              # existing is partial  # noqa: E712
        ex.has_partial_jd == False,                              # incoming is full     # noqa: E712
        func.length(func.coalesce(ex.jd_raw, "")) >= 100,        # …and actually has a JD
    )
    set_ = {
        # JD + partial flag: replace ONLY partial→full; else keep existing (NEVER downgrade)
        "jd_raw":         case((enrich_full, ex.jd_raw), else_=Job.jd_raw),
        "jd_md":          case((enrich_full, ex.jd_md),  else_=Job.jd_md),
        "has_partial_jd": case((enrich_full, False),     else_=Job.has_partial_jd),
        # raw fields: fill NULL from incoming, never overwrite a non-null existing value
        "portal_url":       func.coalesce(Job.portal_url, ex.portal_url),
        "salary_range_raw": func.coalesce(Job.salary_range_raw, ex.salary_range_raw),
        "market":           func.coalesce(Job.market, ex.market),
    }
    # Fire the UPDATE only when something would actually change (no updated_at churn / no
    # pointless writes when a full job is re-seen every scan).
    where = or_(
        enrich_full,
        and_(Job.portal_url.is_(None), ex.portal_url.isnot(None)),
        and_(Job.salary_range_raw.is_(None), ex.salary_range_raw.isnot(None)),
        and_(Job.market.is_(None), ex.market.isnot(None)),
    )
    stmt = (ins.on_conflict_do_update(index_elements=["user_id", "dedup_key"],
                                      set_=set_, where=where)
            # xmax = 0 ⇒ the row was INSERTed (not updated) → distinguishes created vs enriched
            .returning(Job.id, literal_column("(xmax = 0)").label("inserted")))
    row = (await session.execute(stmt)).first()
    if row is not None:
        job = (await session.execute(select(Job).where(Job.id == row.id))).scalar_one()
        return job, bool(row.inserted)
    # No row returned ⇒ conflict where WHERE was false (nothing to enrich) → existing untouched.
    job = (await session.execute(select(Job).where(
        Job.user_id == values["user_id"], Job.dedup_key == values["dedup_key"]))).scalars().first()
    return job, False

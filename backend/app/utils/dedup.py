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

from sqlalchemy import select
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
    """INSERT a job with ON CONFLICT (user_id, dedup_key) DO NOTHING.

    Returns (job, created). created=False means a row with the same (user_id, dedup_key)
    already existed — the existing row is returned. Core insert applies the model's Python
    defaults (id/status/jd_language/…) and the DB server_default (created_at/updated_at)
    for any column not in `values`.

    NOTE: requires the UNIQUE (user_id, dedup_key) index (migration v7_dedup_key_unique) —
    deploy the code that calls this AFTER that migration exists."""
    from app.models.job import Job
    values = dict(values)
    if not values.get("dedup_key"):
        values["dedup_key"] = build_dedup_key(
            values.get("company"), values.get("role"),
            values.get("location"), values.get("portal_url"))
    stmt = (pg_insert(Job).values(**values)
            .on_conflict_do_nothing(index_elements=["user_id", "dedup_key"])
            .returning(Job.id))
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_id is not None:
        job = (await session.execute(select(Job).where(Job.id == new_id))).scalar_one()
        return job, True
    job = (await session.execute(select(Job).where(
        Job.user_id == values["user_id"], Job.dedup_key == values["dedup_key"]))).scalars().first()
    return job, False

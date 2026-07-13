"""Bright Data Web Scraper API (Dataset v3) — async client (BYOK token).

Productionised from the go/no-go probe: sync /scrape with an async trigger→poll→fetch
fallback. Phase 2 = discovery (keyword search); Phase 3 = JD-by-URL enrichment
(collect-by-URL for partial-JD jobs).
"""
import asyncio
import json

import httpx

from app.utils.dedup import _canonical_job_id   # reuse the SAME job-id extraction as dedup

BD_BASE = "https://api.brightdata.com/datasets/v3"
DATASETS = {"linkedin": "gd_lpfll7v5hcqtkxl6l", "indeed": "gd_l4dx9j9sscpvs7no2"}
_POLL_SECONDS, _POLL_TIMEOUT = 10, 900


class BrightDataError(Exception):
    """Bright Data call failed (config / auth / usage). Scanner classifies per-feed, like Apify."""


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def build_input(sub_source: str, keyword: str, location: str, country: str, cfg: dict) -> dict:
    """Per-provider discover-by-keyword schema (field names verified against the live API)."""
    cfg = cfg or {}
    if sub_source == "linkedin":
        d = {"keyword": keyword, "location": location, "country": country,
             "experience_level": cfg.get("experience_level", ""),
             "time_range": cfg.get("time_range", "")}
        if cfg.get("job_type"):
            d["job_type"] = cfg["job_type"]
        return d
    if sub_source == "indeed":
        return {"keyword_search": keyword, "location": location, "country": country,
                "domain": cfg.get("domain", "www.indeed.com"),
                "date_posted": cfg.get("date_posted", "Last 7 days")}
    raise BrightDataError(f"unknown brightdata sub_source: {sub_source}")


def _parse_body(text):
    """Return (records_or_None, obj_or_None): JSON array, NDJSON, or a dict wrapper."""
    text = (text or "").strip()
    if not text:
        return [], None
    try:
        obj = json.loads(text)
        return (obj, None) if isinstance(obj, list) else (None, obj)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    return None, None
        return rows, None


async def _poll_fetch(client, sid, token):
    waited = 0
    while waited < _POLL_TIMEOUT:
        r = await client.get(f"{BD_BASE}/progress/{sid}", headers=_headers(token))
        if r.status_code >= 400:
            raise BrightDataError(f"progress {r.status_code}: {r.text[:200]}")
        status = (r.json().get("status") or "").lower()
        if status in ("ready", "done", "finished", "collected"):
            break
        if status in ("failed", "error", "canceled", "cancelled"):
            raise BrightDataError(f"snapshot {status}")
        await asyncio.sleep(_POLL_SECONDS)
        waited += _POLL_SECONDS
    else:
        raise BrightDataError("snapshot timed out")
    r = await client.get(f"{BD_BASE}/snapshot/{sid}", params={"format": "json"}, headers=_headers(token))
    if r.status_code >= 400:
        raise BrightDataError(f"snapshot fetch {r.status_code}")
    recs, obj = _parse_body(r.text)
    if recs is None and isinstance(obj, dict):
        recs = obj.get("data") or obj.get("records") or []
    return recs or []


async def _resolve_records(client, r, token):
    """Parse a /scrape response into a list of records. Handles: JSON array, NDJSON, an
    async {snapshot_id} (→ poll+fetch), a {data|records|results} wrapper, and a SINGLE
    JSONL record dict (collect-by-URL for one URL → [that dict])."""
    recs, obj = _parse_body(r.text)
    if recs is not None:
        return recs
    if isinstance(obj, dict):
        sid = obj.get("snapshot_id") or obj.get("snapshotId")
        if sid:
            return await _poll_fetch(client, sid, token)
        if any(k in obj for k in ("data", "records", "results")):
            return obj.get("data") or obj.get("records") or obj.get("results") or []
        return [obj]   # a single JSONL record IS the job (collect-by-URL, one url)
    return []


async def brightdata_discover(sub_source, keyword, location, country, cfg, token, limit=25):
    """Trigger a discover-by-keyword scrape and return raw records (list of dicts).
    Cost-aware: limit floors at 10 (the API rejects very low counts)."""
    if not token:
        raise BrightDataError("Bright Data token not configured")
    dataset_id = DATASETS.get(sub_source)
    if not dataset_id:
        raise BrightDataError(f"unknown sub_source {sub_source}")
    q = {"dataset_id": dataset_id, "notify": "false", "include_errors": "true",
         "type": "discover_new", "discover_by": "keyword"}
    payload = {"input": [build_input(sub_source, keyword, location, country, cfg)],
               "limit_per_input": max(int(limit or 25), 10)}
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(f"{BD_BASE}/scrape", params=q, json=payload, headers=_headers(token))
        if r.status_code == 401:
            raise BrightDataError("Bright Data auth failed (check token)")
        if r.status_code == 400 and "not active" in (r.text or "").lower():
            raise BrightDataError("Bright Data account not active")
        if r.status_code >= 400:
            raise BrightDataError(f"scrape {r.status_code}: {r.text[:200]}")
        return await _resolve_records(client, r, token)


# ── Phase 3: JD-by-URL enrichment ───────────────────────────────────────────────
def detect_sub_source(url: str):
    u = (url or "").lower()
    if "linkedin.com" in u:
        return "linkedin"
    if "indeed." in u:
        return "indeed"
    return None


def canonicalize_job_url(url: str, sub_source: str = None) -> str:
    """Rebuild the Bright-Data-acceptable canonical job URL using the SAME job-id
    extraction as the dedup builder (_canonical_job_id) — so the two can never diverge:
    linkedin.com/comm/jobs/view/<id>?trk… → https://www.linkedin.com/jobs/view/<id>."""
    jid = _canonical_job_id(url)   # 'linkedin:<id>' | 'indeed:<jk>' | None
    if jid and jid.startswith("linkedin:"):
        return f"https://www.linkedin.com/jobs/view/{jid.split(':', 1)[1]}"
    if jid and jid.startswith("indeed:"):
        return f"https://www.indeed.com/viewjob?jk={jid.split(':', 1)[1]}"
    return url   # public ATS etc. — pass through unchanged


async def brightdata_collect_by_url(url, sub_source, token, poll_timeout=180):
    """Collect the FULL JD for one job URL (plain /scrape, NO discover param). Canonicalises
    the URL first (matches the dedup builder). Returns the single record dict (with
    job_description_formatted) or None. Cost ~1 credit."""
    if not token:
        raise BrightDataError("Bright Data token not configured")
    dataset_id = DATASETS.get(sub_source)
    if not dataset_id:
        raise BrightDataError(f"unknown sub_source {sub_source}")
    canon = canonicalize_job_url(url, sub_source)
    q = {"dataset_id": dataset_id, "notify": "false", "include_errors": "true"}   # no discover param
    payload = {"input": [{"url": canon}], "limit_per_input": None}
    async with httpx.AsyncClient(timeout=poll_timeout) as client:
        r = await client.post(f"{BD_BASE}/scrape", params=q, json=payload, headers=_headers(token))
        if r.status_code == 401:
            raise BrightDataError("Bright Data auth failed (check token)")
        if r.status_code == 400 and "not active" in (r.text or "").lower():
            raise BrightDataError("Bright Data account not active")
        if r.status_code >= 400:
            raise BrightDataError(f"collect {r.status_code}: {r.text[:200]}")
        recs = await _resolve_records(client, r, token)
        return recs[0] if recs else None


def normalize_brightdata(raw: dict, sub_source: str):
    """Bright Data record → the scanner's Job-shaped dict. None if title/company missing.

    Field mapping: job_title→role, company_name→company, job_location→location,
    job_description_formatted→description, url→(portal_url at save), job_posted_date→posted,
    base_salary→salary, job_seniority_level→seniority (LinkedIn only; Indeed lacks it)."""
    role = raw.get("job_title") or ""
    company = raw.get("company_name") or raw.get("company") or ""
    if not role or not company:
        return None
    return {
        "role": role,
        "company": company,
        "location": raw.get("job_location") or raw.get("location") or "",
        "description": (raw.get("job_description_formatted")
                        or raw.get("description_text") or raw.get("description") or ""),
        "url": raw.get("url") or raw.get("apply_link") or "",
        "salary": raw.get("base_salary") or raw.get("salary") or "",
        "posted": raw.get("job_posted_date") or raw.get("date_posted") or "",
        "seniority": raw.get("job_seniority_level") or "",
    }

"""Bright Data Web Scraper API (Dataset v3) — async discovery client (BYOK token).

Productionised from the go/no-go probe: sync /scrape with an async trigger→poll→fetch
fallback. Discovery only (keyword search) for Phase 2; JD-by-URL enrichment is Phase 3.
"""
import asyncio
import json

import httpx

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
        recs, obj = _parse_body(r.text)
        if recs is None and isinstance(obj, dict):
            sid = obj.get("snapshot_id") or obj.get("snapshotId")
            if sid:                                       # async → poll then fetch
                return await _poll_fetch(client, sid, token)
            recs = obj.get("data") or obj.get("records") or []
        return recs or []


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

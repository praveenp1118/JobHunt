"""
Apify MCP — runs scraping actors and returns structured job data.

Structured JSON from Apify skips Claude parse step (saves tokens).
Pre-filter + S1 scoring still run.
"""
import asyncio
from typing import Optional
from urllib.parse import quote_plus
import httpx

APIFY_BASE = "https://api.apify.com/v2"


# ── Actor input builders ──────────────────────────────────────────────────────
# Field names match each actor's published inputSchema (fetched from the Apify
# API). These differ per actor, so the builders are actor-specific.

def build_linkedin_input(keywords: str, location: str, max_results: int = 25) -> dict:
    """curious_coder/linkedin-jobs-scraper — requires `urls` (LinkedIn job-search
    URLs), plus `count` and `scrapeCompany`. We synthesise the search URL from the
    user's keywords + location."""
    search_url = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(keywords or '')}&location={quote_plus(location or '')}"
    )
    return {
        "urls": [search_url],
        "count": max_results,
        "scrapeCompany": False,
    }


def build_google_jobs_input(keywords: str, location: str, max_results: int = 25) -> dict:
    """johnvc/Google-Jobs-Scraper — requires `query` (string) + `num_results`.
    NOTE: this actor returns 0 results whenever location terms appear (verified:
    'product manager Netherlands' → 0, but 'head of product' → 15), and the separate
    `location` field also yields 0. So we send the bare role keywords only; location
    relevance is handled downstream by market detection + S1/S1d scoring."""
    return {
        "query": keywords or "head of product",
        "num_results": max_results,
    }


def build_indeed_input(keywords: str, location: str, max_results: int = 25) -> dict:
    return {
        "position": keywords,
        "country": _detect_country_code(location),
        "location": location,
        "maxItems": max_results,
    }


def _detect_country_code(location: str) -> str:
    loc = location.lower()
    if any(x in loc for x in ["netherlands", "amsterdam", "nl"]):
        return "NL"
    if any(x in loc for x in ["dubai", "uae"]):
        return "AE"
    if any(x in loc for x in ["singapore", "sg"]):
        return "SG"
    if any(x in loc for x in ["india", "bengaluru", "mumbai"]):
        return "IN"
    return "US"


# ── Actor runner ──────────────────────────────────────────────────────────────

async def run_actor(
    actor_id: str,
    input_data: dict,
    apify_token: str,
    timeout_seconds: int = 300,
    poll_interval: int = 10,
) -> list[dict]:
    """
    Start an Apify actor, wait for completion, return dataset items.
    Timeout after timeout_seconds (default 5 minutes).
    """
    # Apify's REST API uses the tilde form in the path (username~actor-name);
    # a literal "/" 404s. The original actor_id is kept for logging/normalising.
    actor_path = actor_id.replace("/", "~")

    async with httpx.AsyncClient(timeout=30) as client:
        # Start the run. Apify's POST /acts/{id}/runs takes the actor input as the
        # RAW JSON body (NOT wrapped in {"input": ...}) — wrapping it nests the real
        # fields one level down, so required fields like `urls`/`query` go missing
        # and every actor 400s regardless of correct field names.
        start_resp = await client.post(
            f"{APIFY_BASE}/acts/{actor_path}/runs",
            params={"token": apify_token},
            json=input_data,
        )
        start_resp.raise_for_status()
        run_data = start_resp.json().get("data", {})
        run_id = run_data.get("id")
        if not run_id:
            raise ValueError(f"Apify actor start failed: {start_resp.text}")

        print(f"🔄 Apify run started: {actor_id} / {run_id}")

        # Poll for completion
        elapsed = 0
        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_resp = await client.get(
                f"{APIFY_BASE}/acts/{actor_path}/runs/{run_id}",
                params={"token": apify_token},
            )
            status_resp.raise_for_status()
            status_data = status_resp.json().get("data", {})
            status = status_data.get("status", "")

            if status == "SUCCEEDED":
                break
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Apify run {status}: {actor_id}")
            # RUNNING or READY → keep polling

        else:
            raise TimeoutError(f"Apify actor timed out after {timeout_seconds}s: {actor_id}")

        # Fetch dataset items
        dataset_id = status_data.get("defaultDatasetId")
        if not dataset_id:
            return []

        items_resp = await client.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items",
            params={"token": apify_token, "format": "json", "limit": 100},
        )
        items_resp.raise_for_status()
        items = items_resp.json()
        print(f"✅ Apify {actor_id}: {len(items)} items returned")
        return items


# ── Result normaliser ─────────────────────────────────────────────────────────

def normalise_job(raw: dict, actor_id: str) -> Optional[dict]:
    """
    Convert actor-specific output to a standard job dict.
    Returns None if required fields missing.
    """
    if "linkedin" in actor_id.lower():
        return _normalise_linkedin(raw)
    elif "google" in actor_id.lower():
        return _normalise_google(raw)
    elif "indeed" in actor_id.lower():
        return _normalise_indeed(raw)
    else:
        return _normalise_generic(raw)


def _normalise_linkedin(raw: dict) -> Optional[dict]:
    # curious_coder/linkedin-jobs-scraper output: title, companyName, location,
    # link, descriptionText, postedAt, salary.
    title = raw.get("title") or raw.get("jobTitle", "")
    company = raw.get("companyName") or raw.get("company", "")
    if not title or not company:
        return None
    return {
        "role": title,
        "company": company,
        "location": raw.get("location", ""),
        "description": raw.get("descriptionText") or raw.get("description") or raw.get("jobDescription", ""),
        "url": raw.get("link") or raw.get("applyUrl") or raw.get("jobUrl") or raw.get("url", ""),
        "salary": raw.get("salary") or "",
        "posted_at": raw.get("postedAt") or raw.get("publishedAt", ""),
        "source": "apify_linkedin",
    }


def _normalise_google(raw: dict) -> Optional[dict]:
    # johnvc/Google-Jobs-Scraper output: title, company_name, location, description,
    # source_link, share_link. (location is the string "None" when absent.)
    title = raw.get("title") or raw.get("job_title", "")
    company = raw.get("company_name") or raw.get("company") or raw.get("companyName", "")
    if not title or not company:
        return None
    loc = raw.get("location") or ""
    if loc in ("None", "none"):
        loc = ""
    return {
        "role": title,
        "company": company,
        "location": loc,
        "description": raw.get("description", ""),
        "url": raw.get("source_link") or raw.get("share_link") or raw.get("url") or raw.get("applyLink", ""),
        "salary": raw.get("salary", ""),
        "posted_at": raw.get("posted_at") or raw.get("postedAt", ""),
        "source": "apify_google",
    }


def _normalise_indeed(raw: dict) -> Optional[dict]:
    title = raw.get("positionName") or raw.get("title", "")
    company = raw.get("company", "")
    if not title or not company:
        return None
    return {
        "role": title,
        "company": company,
        "location": raw.get("location", ""),
        "description": raw.get("description", ""),
        "url": raw.get("url", ""),
        "salary": raw.get("salary", ""),
        "posted_at": raw.get("postedAt", ""),
        "source": "apify_indeed",
    }


def _normalise_generic(raw: dict) -> Optional[dict]:
    title = raw.get("title") or raw.get("role") or raw.get("jobTitle", "")
    company = raw.get("company") or raw.get("companyName", "")
    if not title or not company:
        return None
    return {
        "role": title,
        "company": company,
        "location": raw.get("location", ""),
        "description": raw.get("description") or raw.get("content", ""),
        "url": raw.get("url") or raw.get("link", ""),
        "salary": raw.get("salary") or raw.get("compensation", ""),
        "posted_at": raw.get("postedAt") or raw.get("date", ""),
        "source": "apify",
    }

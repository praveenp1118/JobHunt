"""
Scanner agents — batch S1 scoring for weekly scan results.
Optimised: score up to 5 JDs against master CV per Claude call.
"""
import json
import re
from typing import Optional

from app.config import settings
from app.utils.usage_logger import log_call


def _get_client(api_key: Optional[str] = None):
    from anthropic import Anthropic
    key = api_key or settings.platform_anthropic_api_key or settings.anthropic_api_key
    if not key:
        raise ValueError("No Anthropic API key configured")
    return Anthropic(api_key=key)


async def batch_score_s1(
    master_cv_md: str,
    jobs: list[dict],
    batch_size: int = 5,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> list[dict]:
    """
    Score multiple JDs against a CV. Returns list of {id, s1_score, key_matches, gaps}
    — one per input job, in order. key_matches/gaps are kept for shape compatibility
    but are NO LONGER requested from the model: only s1_score is used downstream, and
    asking for them ~tripled the output tokens and truncated the JSON, zeroing whole
    batches.
    """
    scored: dict = {}
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        scored.update(await _score_with_retry(master_cv_md, batch, api_key, model))
    # Any job still unscored genuinely failed (even scored alone) → explicit 0.
    return [
        scored.get(job["id"],
                   {"id": job["id"], "s1_score": 0, "key_matches": [], "gaps": ["Score failed"]})
        for job in jobs
    ]


async def _score_with_retry(cv_md, jobs, api_key, model, depth: int = 0) -> dict:
    """Score a batch, then re-score any jobs the model didn't return (truncation/id
    miss) by halving the missing set down to singles. A single bad/truncated response
    can no longer zero a whole batch — only a job that fails even ALONE defaults to 0.
    Bounded by depth and by halving, so worst case is ~2N calls."""
    scored = await _score_once(cv_md, jobs, api_key, model)
    missing = [j for j in jobs if j["id"] not in scored]
    if not missing or depth >= 4 or len(jobs) == 1:
        return scored
    mid = max(1, len(missing) // 2)
    scored.update(await _score_with_retry(cv_md, missing[:mid], api_key, model, depth + 1))
    scored.update(await _score_with_retry(cv_md, missing[mid:], api_key, model, depth + 1))
    return scored


async def _score_once(cv_md, jobs, api_key, model) -> dict:
    """One model call. Returns {job_id: {id, s1_score, key_matches, gaps}} for the
    jobs it successfully scored (a subset if the response was malformed)."""
    client = _get_client(api_key)
    # SHORT, stable ids ("1".."n") — the model never echoes the 64-char jd_hash
    # (which it mangled ~20% of the time → smap miss → spurious 0). Map back after.
    idmap = {str(i + 1): job["id"] for i, job in enumerate(jobs)}

    jobs_text = ""
    for i, job in enumerate(jobs):
        desc = (job.get("description") or "")[:800]
        jobs_text += f"""
Job {i + 1}:
Role: {job.get('role', '')} at {job.get('company', '')}
Location: {job.get('location', '')}
Description: {desc}
---"""

    prompt = f"""Score this candidate's CV fit for each job below.

Score 0-100:
85-100: Excellent fit
70-84: Strong fit
55-69: Good fit, some gaps
40-54: Partial fit
0-39: Poor fit

CANDIDATE CV:
{cv_md[:2500]}

JOBS TO SCORE:
{jobs_text}

Return ONLY a JSON array — one entry per job, using the Job number as "id":
[{{"id": "1", "s1_score": <0-100>}}]"""

    try:
        response = client.messages.create(
            model=model or settings.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        await log_call("batch_score_s1", "scanner", response, model or settings.anthropic_model,
                       entity_label=f"Scanner run · {len(jobs)} jobs")
        parsed = _parse_scores(response.content[0].text)
    except Exception as e:
        print(f"⚠️ Batch S1 scoring error: {e}")
        return {}

    scored = {}
    for entry in (parsed or []):
        real = idmap.get(str(entry.get("id")))
        raw = entry.get("s1_score")
        if real is None or raw is None:
            continue
        try:
            scored[real] = {"id": real, "s1_score": float(raw), "key_matches": [], "gaps": []}
        except (TypeError, ValueError):
            continue
    return scored


def _parse_scores(text: str) -> list:
    """Parse the score array, tolerating code fences AND a truncated tail. The trimmed
    schema has NO nested braces, so we can salvage every complete {...} and drop a
    truncated final one — truncation costs at most the last job (which _score_with_retry
    re-scores), never the whole batch."""
    t = re.sub(r"```json\s*", "", text or "")
    t = re.sub(r"```\s*", "", t).strip()
    try:
        data = json.loads(t)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    out = []
    for obj in re.findall(r"\{[^{}]*\}", t):
        try:
            out.append(json.loads(obj))
        except Exception:
            continue
    return out


async def detect_market_from_job(role: str, company: str, location: str) -> str:
    """Simple rule-based market detection."""
    combined = f"{role} {company} {location}".lower()
    if any(x in combined for x in ["netherlands", "amsterdam", "rotterdam", "nl "]):
        return "NL"
    if any(x in combined for x in ["dubai", "uae", "abu dhabi"]):
        return "Dubai"
    if any(x in combined for x in ["singapore", " sg "]):
        return "SG"
    if any(x in combined for x in ["india", "bangalore", "bengaluru", "mumbai"]):
        return "IN"
    return "EU"

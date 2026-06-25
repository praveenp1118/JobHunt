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
    Score multiple JDs against master CV.
    Batches 5 per Claude call for efficiency.

    Each job dict must have: id, role, company, description
    Returns: list of {id, s1_score, key_matches, gaps}
    """
    results = []
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        batch_results = await _score_batch(master_cv_md, batch, api_key, model)
        results.extend(batch_results)
    return results


async def _score_batch(
    master_cv_md: str,
    jobs: list[dict],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> list[dict]:
    """Score one batch of up to 5 jobs."""
    client = _get_client(api_key)

    jobs_text = ""
    for i, job in enumerate(jobs):
        desc = (job.get("description") or "")[:800]
        jobs_text += f"""
Job {i + 1} (ID: {job['id']}):
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
{master_cv_md[:2500]}

JOBS TO SCORE:
{jobs_text}

Return ONLY JSON array, one entry per job:
[
  {{
    "id": "job id from above",
    "s1_score": <number>,
    "key_matches": ["top 2 matching points"],
    "gaps": ["top 2 gaps"]
  }}
]"""

    try:
        response = client.messages.create(
            model=model or settings.anthropic_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        await log_call("batch_score_s1", "scanner", response, model or settings.anthropic_model,
                       entity_label=f"Scanner run · {len(jobs)} jobs")
        text = response.content[0].text
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        return json.loads(text.strip())
    except Exception as e:
        print(f"⚠️ Batch S1 scoring error: {e}")
        return [
            {"id": job["id"], "s1_score": 0, "key_matches": [], "gaps": ["Score failed"]}
            for job in jobs
        ]


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

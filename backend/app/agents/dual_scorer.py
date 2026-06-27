"""
Dual scoring runner — computes the ATS + Pursuit scores for one CV entity
(master / domain / tailored) against a job, in parallel, and persists them.
"""
import asyncio
from typing import Optional

from app.agents.ats_scorer import compute_ats_score
from app.agents.pursuit_scorer import compute_pursuit_score


async def compute_dual_scores(
    cv_essence: dict,
    cv_md: str,
    jd_text: str,
    cv_entity: str,                    # "master" | "domain" | "tailored"
    job=None,                          # a Job ORM instance to write onto (optional)
    job_posted_days_ago: int = 7,
    anthropic_key: Optional[str] = None,
    ats_model: str = "claude-haiku-4-5",
    pursuit_model: str = "claude-haiku-4-5",
    session=None,                      # commit if provided
) -> dict:
    """Run ATS + Pursuit scoring concurrently (each blocking call is off-thread, so
    `gather` truly parallelizes). When a `job` is supplied, sets `ats_<entity>` /
    `pursuit_<entity>` and merges the breakdown into `job.score_components[entity]`."""
    ats_result, pursuit_result = await asyncio.gather(
        compute_ats_score(cv_essence, jd_text, anthropic_key=anthropic_key, model=ats_model),
        compute_pursuit_score(cv_essence, cv_md, jd_text, job_posted_days_ago=job_posted_days_ago,
                              anthropic_key=anthropic_key, model=pursuit_model),
    )

    if job is not None and cv_entity in ("master", "domain", "tailored"):
        setattr(job, f"ats_{cv_entity}", ats_result.get("total"))
        setattr(job, f"pursuit_{cv_entity}", pursuit_result.get("total"))
        comps = dict(job.score_components or {})
        comps[cv_entity] = {"ats": ats_result, "pursuit": pursuit_result}
        job.score_components = comps
        if session is not None:
            await session.commit()

    return {"ats": ats_result, "pursuit": pursuit_result, "cv_entity": cv_entity}

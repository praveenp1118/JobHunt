"""
Hybrid-RAG scoring pipeline — 3 stages to minimise token cost without losing
quality on saved jobs:

  Stage 1  keyword pre-filter (FREE — match JD vs the CV essence keyword list)
  Stage 2  essence scoring    (cheap model — score JD vs the compact CV essence)
  Stage 3  full-CV scoring     (quality model — only for borderline / no-essence jobs)
  + domain-CV scoring          (only when S1 ≥ a min threshold)

Reuses `scanner_agents.batch_score_s1` for the actual model calls (which logs usage
via the contextvar, so per-stage cost is read off the session-usage accumulator).
"""
import uuid
from typing import Optional

from app.utils.usage_logger import get_session_usage

SCORING_PRESETS = {
    "maximum_quality": {
        "keyword_match_threshold": 2,
        "s1_essence_model": "claude-sonnet-4-6", "s1_essence_reject_below": 40,
        "s1_full_model": "claude-sonnet-4-6", "s1_borderline_low": 40, "s1_borderline_high": 100,
        "domain_score_model": "claude-sonnet-4-6", "domain_score_min_s1": 40,
        "scoring_batch_size": 10,
    },
    "balanced": {
        "keyword_match_threshold": 3,
        "s1_essence_model": "claude-haiku-4-5", "s1_essence_reject_below": 50,
        "s1_full_model": "claude-sonnet-4-6", "s1_borderline_low": 50, "s1_borderline_high": 74,
        "domain_score_model": "claude-haiku-4-5", "domain_score_min_s1": 55,
        "scoring_batch_size": 12,
    },
    "maximum_savings": {
        "keyword_match_threshold": 5,
        "s1_essence_model": "claude-haiku-4-5", "s1_essence_reject_below": 60,
        "s1_full_model": "claude-haiku-4-5", "s1_borderline_low": 60, "s1_borderline_high": 80,
        "domain_score_model": "claude-haiku-4-5", "domain_score_min_s1": 65,
        "scoring_batch_size": 15,
    },
}

CONFIG_FIELDS = [
    "keyword_match_threshold", "s1_essence_model", "s1_essence_reject_below",
    "s1_full_model", "s1_borderline_low", "s1_borderline_high",
    "domain_score_model", "domain_score_min_s1", "scoring_batch_size",
]

# Rough per-job cost of the OLD pipeline (one batched full-CV Sonnet score). Used only
# to show "you saved ₹X vs unoptimized" — not billed.
UNOPT_PER_JOB_INR = 0.58


def config_from_prefs(prefs) -> dict:
    """Build the effective scoring config from a UserPreferences row (or defaults)."""
    base = dict(SCORING_PRESETS["balanced"])
    if prefs:
        for f in CONFIG_FIELDS:
            v = getattr(prefs, f, None)
            if v is not None:
                base[f] = v
    return base


def _essence_text(essence: dict) -> str:
    """Compact text rendering of a CV essence for scoring prompts."""
    if not essence:
        return ""
    p = []
    if essence.get("core_identity"):
        p.append(essence["core_identity"])
    if essence.get("seniority_level"):
        p.append("Seniority: " + str(essence["seniority_level"]))
    if essence.get("years_experience"):
        p.append(f"Experience: {essence['years_experience']} years")
    if essence.get("keywords"):
        p.append("Skills/keywords: " + ", ".join(map(str, essence["keywords"])))
    if essence.get("top_experiences"):
        p.append("Key achievements: " + "; ".join(map(str, essence["top_experiences"])))
    if essence.get("domain_strengths"):
        p.append("Domain strengths: " + ", ".join(f"{k} ({v}/10)" for k, v in essence["domain_strengths"].items()))
    if essence.get("markets"):
        p.append("Markets: " + ", ".join(map(str, essence["markets"])))
    if essence.get("education"):
        p.append("Education: " + ", ".join(map(str, essence["education"])))
    if essence.get("certifications"):
        p.append("Certifications: " + ", ".join(map(str, essence["certifications"])))
    return "\n".join(p)


def _jd_text(job: dict) -> str:
    return job.get("jd_raw") or job.get("description") or job.get("jd_md") or ""


def _score_input(job: dict) -> dict:
    return {"id": job["_rid"], "role": job.get("role", ""), "company": job.get("company", ""),
            "location": job.get("location", ""), "description": _jd_text(job)[:500]}


def _cost() -> float:
    return get_session_usage().get("cost_inr", 0.0)


def _tokens() -> int:
    return get_session_usage().get("tokens", 0)


async def hybrid_rag_score(jobs, master_cv_essence, master_cv_md, domain_cvs, config,
                           anthropic_key) -> dict:
    """Run the 3-stage pipeline. `jobs` are mutated in place with s1/s1d/domain_cv_scores/
    best_domain_cv_id/_stage. Returns {jobs, stats}."""
    from app.agents.scanner_agents import batch_score_s1

    for i, j in enumerate(jobs):
        j["_rid"] = j.get("jd_hash") or j.get("id") or str(i)

    bs = config.get("scoring_batch_size", 12)
    stats = {"total": len(jobs), "stage1_rejected": 0, "stage2_rejected": 0,
             "stage3_scored": 0, "stage2_saved": 0, "saved": 0,
             "tokens_stage2": 0, "tokens_stage3": 0, "cost_inr": 0.0}
    cost_start = _cost()
    results = []

    # ── STAGE 1 — keyword pre-filter (FREE) ──
    kw = [str(k).lower() for k in (master_cv_essence.get("keywords") or [])] if master_cv_essence else []
    stage1 = []
    for job in jobs:
        if kw:
            jd = _jd_text(job).lower()
            matches = sum(1 for k in kw if k and k in jd)
            if matches < config["keyword_match_threshold"]:
                job["_stage"] = "stage1_rejected"
                job["_reject_reason"] = f"keyword_{matches}/{config['keyword_match_threshold']}"
                stats["stage1_rejected"] += 1
                results.append(job)
                continue
            job["_kw_matches"] = matches
        stage1.append(job)

    # ── STAGE 2 — essence scoring (cheap) ──
    essence_text = _essence_text(master_cv_essence)
    stage2 = []
    if stage1 and essence_text and anthropic_key:
        t0 = _tokens()
        scores = await batch_score_s1(essence_text, [_score_input(j) for j in stage1],
                                      batch_size=bs, api_key=anthropic_key, model=config["s1_essence_model"])
        smap = {s["id"]: s.get("s1_score") for s in scores}
        stats["tokens_stage2"] = _tokens() - t0
        for job in stage1:
            sc = smap.get(job["_rid"]) or 0
            job["_s1_essence"] = sc
            if sc < config["s1_essence_reject_below"]:
                job["_stage"] = "stage2_rejected"
                job["_reject_reason"] = f"essence_{sc}<{config['s1_essence_reject_below']}"
                stats["stage2_rejected"] += 1
                results.append(job)
            else:
                stage2.append(job)
    else:
        stage2 = stage1  # no essence → everything goes to full-CV scoring

    # ── STAGE 3 — full-CV scoring (quality) for borderline / no-essence ──
    need_full = []
    for job in stage2:
        es = job.get("_s1_essence")
        if essence_text and es is not None and es >= config["s1_borderline_high"]:
            job["s1"] = es
            job["_stage"] = "stage2_saved"
            stats["stage2_saved"] += 1
        else:
            need_full.append(job)
    if need_full and master_cv_md and anthropic_key:
        t0 = _tokens()
        fscores = await batch_score_s1(master_cv_md, [_score_input(j) for j in need_full],
                                       batch_size=bs, api_key=anthropic_key, model=config["s1_full_model"])
        fmap = {s["id"]: s.get("s1_score") for s in fscores}
        stats["tokens_stage3"] = _tokens() - t0
        for job in need_full:
            job["s1"] = fmap.get(job["_rid"]) or 0
            job["_stage"] = "stage3_scored"
            stats["stage3_scored"] += 1

    # ── Domain-CV scoring (only when S1 ≥ min) ──
    to_domain = [j for j in stage2 if (j.get("s1") or 0) >= config["domain_score_min_s1"]]
    if to_domain and domain_cvs and anthropic_key:
        di = [_score_input(j) for j in to_domain]
        per_job = {j["_rid"]: {} for j in to_domain}
        for dcv in domain_cvs:
            dtext = _essence_text(dcv.get("essence")) or dcv.get("content_md", "")
            if not dtext:
                continue
            dscores = await batch_score_s1(dtext, di, batch_size=bs, api_key=anthropic_key,
                                           model=config["domain_score_model"])
            for s in dscores:
                if s.get("s1_score") is not None:
                    per_job[s["id"]][dcv["id"]] = s["s1_score"]
        for job in to_domain:
            ds = per_job.get(job["_rid"], {})
            valid = {k: v for k, v in ds.items() if v is not None}
            best = max(valid, key=valid.get) if valid else None
            job["domain_cv_scores"] = ds or None
            job["best_domain_cv_id"] = best
            job["s1d"] = valid.get(best) if best else None

    for job in stage2:
        results.append(job)

    stats["cost_inr"] = round(_cost() - cost_start, 2)
    stats["estimated_unoptimized_cost"] = round(stats["total"] * UNOPT_PER_JOB_INR, 2)
    stats["savings_pct"] = (round((1 - stats["cost_inr"] / stats["estimated_unoptimized_cost"]) * 100, 1)
                            if stats["estimated_unoptimized_cost"] else 0.0)
    return {"jobs": results, "stats": stats}


def estimate_scan_cost(config: dict, total_jobs: int, num_domains: int = 0) -> dict:
    """Heuristic per-scan cost estimate for the Settings cost calculator (no API calls)."""
    from app.utils.usage_logger import estimate_anthropic_cost
    # Funnel assumptions (rough): Stage 1 drops ~55%, Stage 2 drops ~35% of survivors,
    # Stage 3 sees borderline survivors. Per-job token estimates are conservative.
    s1_rejected = int(total_jobs * 0.55)
    stage2_jobs = total_jobs - s1_rejected
    stage3_jobs = int(stage2_jobs * 0.45)
    domain_jobs = int(stage2_jobs * 0.45)

    def _per_job(model, in_tok, out_tok):
        return estimate_anthropic_cost(in_tok, out_tok, model)[1]

    c_stage2 = stage2_jobs * _per_job(config["s1_essence_model"], 700, 120)
    c_stage3 = stage3_jobs * _per_job(config["s1_full_model"], 1400, 140)
    c_domain = domain_jobs * max(1, num_domains) * _per_job(config["domain_score_model"], 600, 100)
    total_cost = round(c_stage2 + c_stage3 + c_domain, 2)
    unopt = round(total_jobs * UNOPT_PER_JOB_INR * max(1, (1 + num_domains) * 0.5), 2)
    return {
        "estimated_total_jobs": total_jobs,
        "stage1_rejected_estimate": s1_rejected,
        "stage2_jobs_estimate": stage2_jobs,
        "stage3_jobs_estimate": stage3_jobs,
        "domain_jobs_estimate": domain_jobs,
        "cost_stage2": round(c_stage2, 2),
        "cost_stage3": round(c_stage3, 2),
        "cost_domain": round(c_domain, 2),
        "estimated_cost_inr": total_cost,
        "unoptimized_cost_inr": unopt,
        "savings_pct": round((1 - total_cost / unopt) * 100, 1) if unopt else 0.0,
    }

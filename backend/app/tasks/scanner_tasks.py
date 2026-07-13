"""
Scanner Celery tasks — weekly job scan + RSS + Apify.
Default schedule: Sunday 11 PM IST = 17:30 UTC.
"""
from app.worker import celery_app


def summarize_feed_outcomes(feed_stats):
    """From the per-feed stats list, return (failed, quota, other) for run-status +
    messaging. Pure — no I/O. `failed` = feeds with error=True; `quota` = the
    quota-exhausted subset; `other` = the rest."""
    failed = [s for s in feed_stats if s.get("error")]
    quota = [s for s in failed if s.get("error_kind") == "quota_exhausted"]
    other = [s for s in failed if s.get("error_kind") != "quota_exhausted"]
    return failed, quota, other


@celery_app.task(name="tasks.weekly_job_scan", bind=True, max_retries=1)
def weekly_job_scan(self):
    """
    Weekly scan: run all active feeds for all users.
    - RSS feeds: fetch and parse
    - Apify feeds: run actors and collect structured data
    - Pre-filter → S1 score → save to DB
    """
    import asyncio
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_weekly_scan_async())
    finally:
        # Dispose the engine's pool in THIS loop so the next task (new loop)
        # doesn't reuse connections bound to a now-closed loop.
        loop.run_until_complete(engine.dispose())
        loop.close()


async def _weekly_scan_async():
    from datetime import datetime, timezone
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials
    from app.models.domain import UserFeed
    from app.models.admin import RunLog, RunType, RunStatus
    from app.utils.encryption import decrypt_if_present
    from app.config import settings

    print("🔄 Starting weekly job scan...")
    total_found = 0
    total_added = 0
    all_feed_stats = []
    all_rag_stats = {}
    errors = []

    async with AsyncSessionLocal() as session:
        # Log run start
        run_log = RunLog(
            run_type=RunType.weekly_scan,
            status=RunStatus.running,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run_log)
        await session.flush()
        run_log_id = run_log.id
        # Job commits now run on per-user sessions, not this outer one, so nothing else
        # will persist the run_log before the finalize — commit the "running" row now.
        await session.commit()

        try:
            # Get all active users with credentials
            result = await session.execute(
                select(User, UserCredentials)
                .join(UserCredentials, UserCredentials.user_id == User.id)
                .where(User.is_active == True)
            )
            user_creds = result.all()

            from app.utils.subscription import is_entitled
            for user, creds in user_creds:
                try:
                    # Skip un-entitled users — the scheduled scan calls Claude for
                    # scoring, and an inert (invite-lapsed / never-entitled) account
                    # must not spend tokens on the platform's schedule.
                    if not is_entitled(user):
                        continue

                    # Per-user session: a DB error for THIS user rolls back on exit of the
                    # `async with` and cannot poison the next user's scan or the outer
                    # run_log session. _scan_feeds_for_user commits internally exactly as
                    # before — just its OWN session now.
                    async with AsyncSessionLocal() as user_session:
                        feeds = (await user_session.execute(
                            select(UserFeed).where(
                                UserFeed.user_id == user.id,
                                UserFeed.is_active == True,
                            )
                        )).scalars().all()
                        if not feeds:
                            continue

                        # Get API keys
                        apify_token = None
                        if creds.apify_token_enc:
                            apify_token = decrypt_if_present(creds.apify_token_enc)
                        if not apify_token:
                            apify_token = settings.platform_apify_token

                        # Bright Data is BYOK-only (no platform fallback) — skip if unset.
                        brightdata_token = (decrypt_if_present(creds.brightdata_token_enc)
                                            if creds.brightdata_token_enc else None)

                        anthropic_key = None
                        if creds.anthropic_api_key_enc:
                            anthropic_key = decrypt_if_present(creds.anthropic_api_key_enc)
                        if not anthropic_key:
                            anthropic_key = settings.platform_anthropic_api_key or settings.anthropic_api_key

                        found, added, feed_stats, rag_stats = await _scan_feeds_for_user(
                            user=user,
                            feeds=feeds,
                            apify_token=apify_token,
                            brightdata_token=brightdata_token,
                            anthropic_key=anthropic_key,
                            session=user_session,
                        )

                    # Aggregate in-memory results (plain values — safe after the session closes).
                    total_found += found
                    total_added += added
                    all_feed_stats.extend(feed_stats)
                    for k in ("total", "stage1_rejected", "stage2_rejected", "stage2_saved",
                              "stage3_scored", "tokens_stage2", "tokens_stage3", "cost_inr",
                              "estimated_unoptimized_cost"):
                        all_rag_stats[k] = round(all_rag_stats.get(k, 0) + (rag_stats.get(k, 0) or 0), 2)

                except Exception as e:
                    err = f"User {user.email}: {e}"
                    errors.append(err)
                    print(f"❌ {err}")

            # Update run log
            run_log_result = await session.execute(
                select(RunLog).where(RunLog.id == run_log_id)
            )
            run_log = run_log_result.scalar_one()
            feed_failed, quota_feeds, other_failed = summarize_feed_outcomes(all_feed_stats)
            run_log.status = (RunStatus.success
                              if not errors and not feed_failed
                              else RunStatus.partial)
            run_log.jobs_found = total_found
            run_log.jobs_added = total_added
            # Accumulate this run's API usage (rows logged since the scan started).
            from app.models.usage import APIUsageLog
            urows = (await session.execute(
                select(APIUsageLog).where(APIUsageLog.created_at >= run_log.started_at)
            )).scalars().all()
            usage_summary = {
                "anthropic_tokens": sum(r.total_tokens or 0 for r in urows if r.provider == "anthropic"),
                "anthropic_inr": round(sum(r.estimated_cost_inr or 0 for r in urows if r.provider == "anthropic"), 2),
                "apify_runs": sum(r.runs_returned or 0 for r in urows if r.provider == "apify"),
                "apify_usd": round(sum(r.estimated_cost_usd or 0 for r in urows if r.provider == "apify"), 3),
            }
            if all_rag_stats.get("estimated_unoptimized_cost"):
                all_rag_stats["savings_pct"] = round(
                    (1 - all_rag_stats.get("cost_inr", 0) / all_rag_stats["estimated_unoptimized_cost"]) * 100, 1)
            # Aggregate pre-filter funnel — compare across scans to measure the pruned
            # blocklist's impact (passed/scored up, saved ~flat, cost_inr the S1 delta).
            prefilter = {
                "raw":                sum(s.get("raw_results", 0) for s in all_feed_stats),
                "passed_prefilter":   sum(s.get("pre_filter_passed", 0) for s in all_feed_stats),
                "rejected_prefilter": sum(s.get("pre_filter_failed", 0) for s in all_feed_stats),
                "scored":             sum(s.get("s1_scored", 0) for s in all_feed_stats),
                "saved":              sum(s.get("saved", 0) for s in all_feed_stats),
            }
            print(f"📊 pre-filter funnel: {prefilter['raw']} raw → {prefilter['passed_prefilter']} passed "
                  f"→ {prefilter['scored']} scored → {prefilter['saved']} saved · RAG ₹{all_rag_stats.get('cost_inr')}")
            run_log.details = {"feeds_run": len(all_feed_stats), "feeds_summary": all_feed_stats,
                               "usage_summary": usage_summary, "rag_stats": all_rag_stats or None,
                               "prefilter": prefilter,
                               "apify_quota_exhausted": bool(quota_feeds),
                               "feed_failures": len(feed_failed)}
            run_log.completed_at = datetime.now(timezone.utc)
            run_log.duration_seconds = (run_log.completed_at - run_log.started_at).total_seconds()
            reason_bits = list(errors)
            if quota_feeds:
                names = ", ".join(s.get("feed_name", "?") for s in quota_feeds[:3])
                reason_bits.append(
                    f"Apify usage/credit limit reached on {names} — top up your Apify "
                    "account or wait for the monthly reset")
            if other_failed:
                reason_bits.append(f"{len(other_failed)} feed(s) failed")
            if reason_bits:
                run_log.error_message = "; ".join(str(b) for b in reason_bits[:5])

            await session.commit()

        except Exception as e:
            print(f"❌ Weekly scan failed: {e}")
            run_log_result = await session.execute(
                select(RunLog).where(RunLog.id == run_log_id)
            )
            rl = run_log_result.scalar_one_or_none()
            if rl:
                rl.status = RunStatus.error
                rl.error_message = str(e)
                rl.completed_at = datetime.now(timezone.utc)
            await session.commit()
            raise

    print(f"✅ Weekly scan complete: {total_found} found, {total_added} added")
    return {"found": total_found, "added": total_added, "errors": errors}


async def _scan_feeds_for_user(user, feeds, apify_token, anthropic_key, session, brightdata_token=None):
    """Scan all feeds for a single user."""
    from app.utils.usage_logger import set_usage_user
    set_usage_user(user.id)  # attribute all agent calls in this scan to this user
    from app.mcp.apify_mcp import (run_actor, normalise_job, build_linkedin_input,
                                   build_google_jobs_input, ApifyQuotaExhausted)
    from app.mcp.rss_mcp import fetch_rss_feed
    from app.agents.jd_agents import pre_filter_jd, compute_jd_hash, build_user_keywords
    from app.agents.scanner_agents import batch_score_s1, detect_market_from_job
    import uuid
    from app.models.job import Job, JobSource, JobStatus
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.domain import IndustryVertical
    from sqlalchemy import select

    # Load master CV
    master_result = await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )
    master = master_result.scalars().first()
    master_cv_md = master.content_md if master else ""

    from app.models.user import UserPreferences
    # .first() (not scalar_one_or_none) — tolerant of any pre-existing duplicate prefs rows
    # (scalar_one_or_none raises "Multiple rows were found" and aborts the whole user's scan).
    prefs = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )).scalars().first()
    threshold = prefs.s1_min_threshold if prefs else 65

    # Per-feed keyword sets (Option B): each feed pre-filters with its OWN
    # keywords, not one combined pool across all feeds.
    target_roles = prefs.target_roles if prefs else None
    feed_by_id = {str(f.id): f for f in feeds}
    feed_keywords_map = {
        str(f.id): build_user_keywords(target_roles, [f.search_keywords or f.keywords])
        for f in feeds
    }
    fallback_keywords = build_user_keywords(target_roles)

    # Rich per-feed breakdown for the Activity dashboard (run_log.details)
    stats = {
        str(f.id): {
            "feed_name": f.name, "feed_type": f.feed_type,
            "raw_results": 0, "pre_filter_passed": 0, "pre_filter_failed": 0,
            "s1_scored": 0, "above_threshold": 0, "duplicates": 0, "saved": 0,
            "rejected": [], "saved_examples": [], "note": None,
            "error": False, "error_kind": None,   # None | "quota_exhausted" | "failed"
        }
        for f in feeds
    }

    def _reject(fid, job, reason, s1=None, s1d=None, domain_scores=None, best=None):
        st = stats.get(fid)
        if st is not None and len(st["rejected"]) < 25:  # cap to keep the JSON small
            st["rejected"].append({
                "title": (job.get("role") or "")[:80],
                "company": (job.get("company") or "")[:60],
                "s1": s1,
                "s1d": s1d,
                "domain_scores": domain_scores or None,
                "best_domain_cv": best,
                "reason": reason,
            })

    all_raw_jobs = []

    # ── 1. Fetch ────────────────────────────────────────────────────────────
    for feed in feeds:
        fid = str(feed.id)
        try:
            if feed.feed_type == "rss":
                raw_jobs = await fetch_rss_feed(feed.url_or_actor)
                for j in raw_jobs:
                    j["feed_id"] = fid
                    j["source"] = "rss"
                stats[fid]["raw_results"] += len(raw_jobs)
                all_raw_jobs.extend(raw_jobs)
                if not raw_jobs:
                    stats[fid]["note"] = "Feed returned no results"

            elif feed.feed_type == "apify":
                if not apify_token:
                    stats[fid]["note"] = "Apify actor not triggered — no token configured"
                    continue
                keywords = feed.search_keywords or feed.keywords or "head of product VP product"
                location = feed.location or "Netherlands"
                actor_id = feed.url_or_actor
                match = (feed.actor_name or actor_id or "").lower()
                if "linkedin" in match:
                    input_data = build_linkedin_input(keywords, location)
                elif "google" in match:
                    input_data = build_google_jobs_input(keywords, location)
                else:
                    input_data = {"query": keywords, "maxItems": 25}

                raw_items = await run_actor(actor_id, input_data, apify_token, timeout_seconds=180)
                normalise_hint = feed.actor_name or actor_id
                count = 0
                for raw in raw_items:
                    normalised = normalise_job(raw, normalise_hint)
                    if normalised:
                        normalised["feed_id"] = fid
                        all_raw_jobs.append(normalised)
                        count += 1
                stats[fid]["raw_results"] += count
                try:
                    from app.utils.usage_logger import log_apify_usage
                    req = input_data.get("count") or input_data.get("num_results") or input_data.get("maxItems") or 0
                    # Apify cost is approximate (PAY_PER_EVENT actors ~ $0.005 / result).
                    await log_apify_usage(
                        session, user.id, actor_id=actor_id, feed_label=feed.name,
                        runs_requested=req, runs_returned=len(raw_items), jobs_saved=count,
                        cost_usd=round(len(raw_items) * 0.005, 4), entity_id=str(feed.id))
                except Exception as e:
                    print(f"⚠️ apify usage log failed: {e}")
                if count == 0:
                    stats[fid]["note"] = "Apify actor returned no usable results"

            elif feed.feed_type == "brightdata":
                # Bright Data discovery — BYOK. This branch only FETCHES + NORMALISES; the
                # results then flow through the SAME shared pipeline as every other source:
                # §2 pre-filter (free) BEFORE any paid scoring → §3 dedup_key → §4 upsert
                # (ON CONFLICT). So a Bright Data LinkedIn job with the same job-id as an
                # Apify/Gmail one collapses to one row (the Phase-1 payoff) with zero
                # Bright-Data-specific dedup code.
                if not brightdata_token:
                    stats[fid]["note"] = "Bright Data not triggered — no token configured"
                    continue
                from app.utils.brightdata_client import (brightdata_discover,
                                                         normalize_brightdata, BrightDataError)
                cfg = feed.provider_config or {}
                sub = feed.url_or_actor  # 'linkedin' | 'indeed'
                keyword = feed.search_keywords or feed.keywords or "head of product"
                try:
                    raw_items = await brightdata_discover(
                        sub_source=sub, keyword=keyword, location=feed.location or "",
                        country=cfg.get("country") or "", cfg=cfg,
                        token=brightdata_token, limit=cfg.get("limit", 25))  # cost-aware default 25
                except BrightDataError as e:
                    stats[fid]["error"] = True
                    stats[fid]["error_kind"] = "failed"
                    stats[fid]["note"] = f"Bright Data error: {e}"
                    print(f"⚠️ Feed {feed.name}: Bright Data — {e}")
                    continue
                count = 0
                for raw in raw_items:
                    n = normalize_brightdata(raw, sub)
                    if not n:
                        continue
                    # FREE provider-side seniority drop BEFORE the shared pre-filter/scoring —
                    # LinkedIn exposes job_seniority_level; Indeed doesn't (seniority="").
                    if (n.get("seniority") or "").strip().lower() in ("internship", "entry level"):
                        continue
                    n["feed_id"] = fid
                    n["source"] = "brightdata"
                    all_raw_jobs.append(n)
                    count += 1
                stats[fid]["raw_results"] += count
                try:
                    from app.utils.usage_logger import log_brightdata_usage
                    await log_brightdata_usage(
                        session, user.id, sub_source=sub, feed_label=feed.name,
                        runs_requested=cfg.get("limit", 25), runs_returned=len(raw_items),
                        jobs_saved=count, entity_id=str(feed.id))
                except Exception as e:
                    print(f"⚠️ brightdata usage log failed: {e}")
                if count == 0:
                    stats[fid]["note"] = "Bright Data returned no usable results"

        except ApifyQuotaExhausted as e:
            stats[fid]["error"] = True
            stats[fid]["error_kind"] = "quota_exhausted"
            stats[fid]["note"] = (
                "Apify credits/usage limit reached on your token — top up your Apify "
                f"account or wait for the monthly reset. ({e.reason})")
            print(f"⚠️ Feed {feed.name}: Apify quota exhausted — {e.reason}")
            continue
        except Exception as e:
            stats[fid]["error"] = True
            stats[fid]["error_kind"] = "failed"
            stats[fid]["note"] = f"Feed error: {e}"
            print(f"⚠️ Feed {feed.name} failed: {e}")
            continue

    found = len(all_raw_jobs)

    # ── 2. Pre-filter (rule-based, free) ────────────────────────────────────
    filtered_jobs = []
    for job in all_raw_jobs:
        fid = job.get("feed_id")
        raw_text = f"{job.get('role', '')} {job.get('description', '')}"
        result = pre_filter_jd(raw_text, user_keywords=feed_keywords_map.get(fid, fallback_keywords))
        if result["passed"]:
            if fid in stats:
                stats[fid]["pre_filter_passed"] += 1
            filtered_jobs.append(job)
        else:
            if fid in stats:
                stats[fid]["pre_filter_failed"] += 1
            _reject(fid, job, f"pre_filter_fail: {result.get('reason_code') or 'rejected'}", s1=0)

    # ── 3. Dedup (canonical dedup_key vs DB AND within this batch) ───────────
    # Pre-check on dedup_key avoids paying Claude to score a job we already have; the
    # ON CONFLICT at insert (upsert_job) is the ultimate parallel-source race guard.
    from app.utils.dedup import build_dedup_key
    new_jobs = []
    seen_keys = set()  # guard against duplicate cards within the same scan
    for job in filtered_jobs:
        fid = job.get("feed_id")
        raw_text = f"{job.get('role', '')} {job.get('company', '')} {job.get('description', '')}"
        job["jd_hash"] = compute_jd_hash(raw_text)   # kept (community + backwards-compat)
        dk = build_dedup_key(job.get("company", ""), job.get("role", ""),
                             job.get("location", ""), job.get("url"))
        job["dedup_key"] = dk
        # .first() (not scalar_one_or_none) — tolerant of any pre-existing dup rows.
        existing = (await session.execute(
            select(Job.id).where(Job.dedup_key == dk, Job.user_id == user.id)
        )).scalars().first()
        if dk not in seen_keys and not existing:
            seen_keys.add(dk)
            new_jobs.append(job)
        else:
            if fid in stats:
                stats[fid]["duplicates"] += 1
            _reject(fid, job, "duplicate")

    # ── 4 + 5. Hybrid-RAG scoring + threshold save ──────────────────────────
    from app.agents.rag_scorer import hybrid_rag_score, config_from_prefs
    config = config_from_prefs(prefs)
    master_essence = master.essence_json if master else None

    # Active domain CVs — essence preferred (cheap), content as fallback.
    domain_cv_labels = {}
    domain_cvs_input = []
    if new_jobs:
        dcv_rows = (await session.execute(
            select(DomainCV.id, DomainCV.content_md, DomainCV.essence_json,
                   IndustryVertical.label, DomainCV.country_code)
            .outerjoin(IndustryVertical, IndustryVertical.id == DomainCV.industry_id)
            .where(DomainCV.user_id == user.id, DomainCV.status == CVStatus.active,
                   DomainCV.content_md.isnot(None))
        )).all()
        domain_cv_labels = {str(did): f"{ind or 'Domain'} × {cc or '—'}"
                            for did, _c, _e, ind, cc in dcv_rows}
        domain_cvs_input = [{"id": str(did), "content_md": c, "essence": e}
                            for did, c, e, _i, _cc in dcv_rows]

    rag_stats = {"total": len(new_jobs), "stage1_rejected": 0, "stage2_rejected": 0,
                 "stage2_saved": 0, "stage3_scored": 0, "pending": 0, "tokens_stage2": 0,
                 "tokens_stage3": 0, "cost_inr": 0.0, "estimated_unoptimized_cost": 0.0, "savings_pct": 0.0}
    rag_jobs = new_jobs
    timing = (prefs.scoring_timing if prefs else "immediate")

    if new_jobs and timing == "immediate" and anthropic_key:
        # Real-time scoring — full 3-stage RAG.
        rag = await hybrid_rag_score(new_jobs, master_essence, master_cv_md,
                                     domain_cvs_input, config, anthropic_key)
        rag_jobs, rag_stats = rag["jobs"], rag["stats"]
    elif new_jobs and timing in ("overnight", "manual"):
        # Defer scoring — only the FREE Stage-1 keyword filter runs now; survivors saved 'pending'.
        kw = [str(k).lower() for k in ((master_essence or {}).get("keywords") or [])]
        thr = config["keyword_match_threshold"]
        rej = 0
        for job in new_jobs:
            if kw:
                jd = (job.get("jd_raw") or job.get("description") or "").lower()
                if sum(1 for k in kw if k and k in jd) < thr:
                    job["_stage"] = "stage1_rejected"
                    job["_reject_reason"] = f"keyword(pending mode)"
                    rej += 1
                    continue
            job["_stage"] = "pending"
        rag_stats["stage1_rejected"] = rej
        rag_stats["pending"] = len(new_jobs) - rej

    def _labelled(dscores):
        return {domain_cv_labels.get(k, k): v for k, v in (dscores or {}).items()}

    # Save RAG-survivors above threshold; record RAG-rejected jobs (cost saved upstream).
    added = 0
    saved_job_objs = []  # scored (non-pending) jobs, for optional dual scoring below
    source_map = {"rss": JobSource.rss, "apify_linkedin": JobSource.apify,
                  "apify_google": JobSource.apify, "apify": JobSource.apify,
                  "brightdata": JobSource.brightdata}
    for job in rag_jobs:
        fid = job.get("feed_id")
        try:
            stage = job.get("_stage")
            if stage in ("stage1_rejected", "stage2_rejected"):
                _reject(fid, job, job.get("_reject_reason") or stage, s1=job.get("_s1_essence"))
                continue

            if fid in stats:
                stats[fid]["s1_scored"] += 1
            job_hash = job.get("jd_hash", "")
            pending = stage == "pending"  # overnight/manual mode → saved unscored
            s1 = job.get("s1")
            feed = feed_by_id.get(fid)

            dscores = job.get("domain_cv_scores") or {}  # {dcv_id_str: score}
            best_dcv_id_str = job.get("best_domain_cv_id")
            best_s1d = job.get("s1d")

            # S1d (best domain CV) drives the decision when available; else S1.
            has_domain = best_s1d is not None
            decision = best_s1d if has_domain else s1

            # Gate by threshold (when we could score). Pending jobs aren't gated yet.
            if not pending and decision is not None and decision < threshold:
                _reject(fid, job, "below_threshold", s1=s1, s1d=best_s1d,
                        domain_scores=_labelled(dscores), best=domain_cv_labels.get(best_dcv_id_str))
                continue
            if not pending and decision is not None and fid in stats:
                stats[fid]["above_threshold"] += 1
            if fid in stats and len(stats[fid]["saved_examples"]) < 12:
                stats[fid]["saved_examples"].append({
                    "title": (job.get("role") or "")[:80],
                    "company": (job.get("company") or "")[:60],
                    "s1": s1, "s1d": best_s1d,
                    "domain_scores": _labelled(dscores),
                    "best_domain_cv": domain_cv_labels.get(best_dcv_id_str),
                    "decision": f"{stage} · " + (f"s1d={best_s1d}" if has_domain else f"s1={s1}"),
                })

            source = source_map.get(job.get("source", "rss"), JobSource.rss)
            market = await detect_market_from_job(job.get("role", ""), job.get("company", ""), job.get("location", ""))

            # JD text — strip any stray HTML (RSS content / some Apify actors) before storing.
            jd_text = job.get("description") or ""
            if jd_text and "<" in jd_text:
                from bs4 import BeautifulSoup
                jd_text = BeautifulSoup(jd_text, "html.parser").get_text(separator="\n")
            jd_text = jd_text[:50000]

            from app.utils.dedup import upsert_job
            _saved, _created = await upsert_job(session, dict(
                user_id=user.id,
                company=job.get("company", "Unknown"),
                role=job.get("role", "Unknown"),
                location=job.get("location"),
                market=market,
                jd_hash=job_hash,
                dedup_key=job.get("dedup_key"),
                jd_raw=jd_text,
                jd_md=jd_text,
                portal_url=job.get("url"),
                source=source,
                status=JobStatus.new,
                s1=s1,
                s1d=best_s1d,
                scoring_status=("pending" if pending else "scored"),
                domain_cv_scores=(dscores or None),
                best_domain_cv_id=(uuid.UUID(best_dcv_id_str) if best_dcv_id_str else None),
                salary_range_raw=job.get("salary"),
                source_feed_id=feed.id if feed else None,
                detected_domain_cv_id=feed.domain_cv_id if feed else None,
            ))
            if not _created:      # a parallel source already saved this exact job
                if fid in stats:
                    stats[fid]["duplicates"] += 1
                continue
            if not pending:
                saved_job_objs.append(_saved)
            added += 1
            if fid in stats:
                stats[fid]["saved"] += 1
        except Exception as e:
            print(f"⚠️ Failed to save job: {e}")
            continue

    await session.commit()

    # Optional ATS + Pursuit dual scoring on saved jobs (gated — off by default; adds ~₹0.15/job).
    if (getattr(prefs, "auto_dual_score_on_scan", False) and anthropic_key
            and master_essence and saved_job_objs):
        from app.agents.dual_scorer import compute_dual_scores
        dcv_by_id = {d["id"]: d for d in domain_cvs_input}
        for j in saved_job_objs:
            try:
                jd = j.jd_md or j.jd_raw or ""
                await compute_dual_scores(master_essence, master_cv_md, jd, "master",
                                          job=j, anthropic_key=anthropic_key)
                if j.best_domain_cv_id:
                    d = dcv_by_id.get(str(j.best_domain_cv_id))
                    if d:
                        await compute_dual_scores(d.get("essence") or master_essence,
                                                  d.get("content_md") or "", jd, "domain",
                                                  job=j, anthropic_key=anthropic_key)
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ dual score (scan) failed: {e}")
        await session.commit()

    print(f"✅ User {user.email}: {found} found, {added} added (RAG ₹{rag_stats.get('cost_inr')})")
    return found, added, list(stats.values()), rag_stats

"""
Scanner Celery tasks — weekly job scan + RSS + Apify.
Default schedule: Sunday 11 PM IST = 17:30 UTC.
"""
from app.worker import celery_app


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

        try:
            # Get all active users with credentials
            result = await session.execute(
                select(User, UserCredentials)
                .join(UserCredentials, UserCredentials.user_id == User.id)
                .where(User.is_active == True)
            )
            user_creds = result.all()

            for user, creds in user_creds:
                try:
                    # Get user's active feeds
                    feeds_result = await session.execute(
                        select(UserFeed).where(
                            UserFeed.user_id == user.id,
                            UserFeed.is_active == True,
                        )
                    )
                    feeds = feeds_result.scalars().all()

                    if not feeds:
                        continue

                    # Get API keys
                    apify_token = None
                    if creds.apify_token_enc:
                        apify_token = decrypt_if_present(creds.apify_token_enc)
                    if not apify_token:
                        apify_token = settings.platform_apify_token

                    anthropic_key = None
                    if creds.anthropic_api_key_enc:
                        anthropic_key = decrypt_if_present(creds.anthropic_api_key_enc)
                    if not anthropic_key:
                        anthropic_key = settings.platform_anthropic_api_key or settings.anthropic_api_key

                    found, added, feed_stats = await _scan_feeds_for_user(
                        user=user,
                        feeds=feeds,
                        apify_token=apify_token,
                        anthropic_key=anthropic_key,
                        session=session,
                    )
                    total_found += found
                    total_added += added
                    all_feed_stats.extend(feed_stats)

                except Exception as e:
                    err = f"User {user.email}: {e}"
                    errors.append(err)
                    print(f"❌ {err}")

            # Update run log
            run_log_result = await session.execute(
                select(RunLog).where(RunLog.id == run_log_id)
            )
            run_log = run_log_result.scalar_one()
            run_log.status = RunStatus.success if not errors else RunStatus.partial
            run_log.jobs_found = total_found
            run_log.jobs_added = total_added
            run_log.details = {"feeds_run": len(all_feed_stats), "feeds_summary": all_feed_stats}
            run_log.completed_at = datetime.now(timezone.utc)
            run_log.duration_seconds = (run_log.completed_at - run_log.started_at).total_seconds()
            if errors:
                run_log.error_message = "; ".join(errors[:5])

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


async def _scan_feeds_for_user(user, feeds, apify_token, anthropic_key, session):
    """Scan all feeds for a single user."""
    from app.mcp.apify_mcp import run_actor, normalise_job, build_linkedin_input, build_google_jobs_input
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
    prefs = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )).scalar_one_or_none()
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
                if count == 0:
                    stats[fid]["note"] = "Apify actor returned no usable results"

        except Exception as e:
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

    # ── 3. Dedup (vs DB AND within this batch) ──────────────────────────────
    new_jobs = []
    seen_hashes = set()  # guard against duplicate cards within the same scan
    for job in filtered_jobs:
        fid = job.get("feed_id")
        raw_text = f"{job.get('role', '')} {job.get('company', '')} {job.get('description', '')}"
        jd_hash = compute_jd_hash(raw_text)
        # .first() (not scalar_one_or_none) — tolerant of any pre-existing dup rows.
        existing = (await session.execute(
            select(Job.id).where(Job.jd_hash == jd_hash, Job.user_id == user.id)
        )).scalars().first()
        if jd_hash not in seen_hashes and not existing:
            seen_hashes.add(jd_hash)
            job["jd_hash"] = jd_hash
            new_jobs.append(job)
        else:
            if fid in stats:
                stats[fid]["duplicates"] += 1
            _reject(fid, job, "duplicate")

    # ── 4. S1 scoring ───────────────────────────────────────────────────────
    # 4a. S1 = base fit vs the MASTER CV (universal baseline) for every job.
    scored_map = {}
    if new_jobs and master_cv_md and anthropic_key:
        score_inputs = [
            {"id": j.get("jd_hash", str(i)), "role": j.get("role", ""), "company": j.get("company", ""),
             "location": j.get("location", ""), "description": j.get("description", "")[:500]}
            for i, j in enumerate(new_jobs)
        ]
        scores = await batch_score_s1(master_cv_md, score_inputs, api_key=anthropic_key)
        scored_map = {s["id"]: s for s in scores}

    # 4b. Score every job against ALL of the user's active domain CVs (not just the
    #     feed's linked one). domain_scores_by_job[hash] = {dcv_id_str: score}; the
    #     best one drives the threshold decision + Tailor pre-select.
    #     Token cost: N new jobs × M active domain CVs (each batched 5/call).
    domain_scores_by_job = {}
    domain_cv_labels = {}
    if new_jobs and anthropic_key:
        dcv_rows = (await session.execute(
            select(DomainCV.id, DomainCV.content_md, IndustryVertical.label, DomainCV.country_code)
            .outerjoin(IndustryVertical, IndustryVertical.id == DomainCV.industry_id)
            .where(DomainCV.user_id == user.id, DomainCV.status == CVStatus.active,
                   DomainCV.content_md.isnot(None))
        )).all()
        domain_cv_labels = {str(dcv_id): f"{ind or 'Domain'} × {cc or '—'}"
                            for dcv_id, _content, ind, cc in dcv_rows}
        active_dcvs = [(dcv_id, content) for dcv_id, content, _ind, _cc in dcv_rows if content]
        if active_dcvs:
            dscore_inputs = [
                {"id": j.get("jd_hash", str(i)), "role": j.get("role", ""), "company": j.get("company", ""),
                 "location": j.get("location", ""), "description": j.get("description", "")[:500]}
                for i, j in enumerate(new_jobs)
            ]
            for dcv_id, content in active_dcvs:
                for s in await batch_score_s1(content, dscore_inputs, api_key=anthropic_key):
                    domain_scores_by_job.setdefault(s["id"], {})[str(dcv_id)] = s.get("s1_score")

    def _labelled(dscores):
        return {domain_cv_labels.get(k, k): v for k, v in (dscores or {}).items()}

    # ── 5. Threshold + save ─────────────────────────────────────────────────
    # Decision score: use S1d when the feed has a linked domain CV, else S1.
    added = 0
    source_map = {"rss": JobSource.rss, "apify_linkedin": JobSource.apify,
                  "apify_google": JobSource.apify, "apify": JobSource.apify}
    for job in new_jobs:
        fid = job.get("feed_id")
        if fid in stats:
            stats[fid]["s1_scored"] += 1
        try:
            job_hash = job.get("jd_hash", "")
            s1 = scored_map.get(job_hash, {}).get("s1_score")
            feed = feed_by_id.get(fid)

            # Best-fit domain CV across ALL active domain CVs.
            dscores = domain_scores_by_job.get(job_hash, {})  # {dcv_id_str: score}
            valid = {k: v for k, v in dscores.items() if v is not None}
            best_dcv_id_str = max(valid, key=valid.get) if valid else None
            best_s1d = valid.get(best_dcv_id_str) if best_dcv_id_str else None

            # S1d (best domain CV) drives the decision when available; else S1.
            has_domain = best_s1d is not None
            decision = best_s1d if has_domain else s1

            # Gate by threshold (when we could score). No score → save (can't gate).
            if decision is not None and decision < threshold:
                _reject(fid, job, "below_threshold", s1=s1, s1d=best_s1d,
                        domain_scores=_labelled(dscores), best=domain_cv_labels.get(best_dcv_id_str))
                continue
            if decision is not None and fid in stats:
                stats[fid]["above_threshold"] += 1
            if fid in stats and len(stats[fid]["saved_examples"]) < 12:
                stats[fid]["saved_examples"].append({
                    "title": (job.get("role") or "")[:80],
                    "company": (job.get("company") or "")[:60],
                    "s1": s1, "s1d": best_s1d,
                    "domain_scores": _labelled(dscores),
                    "best_domain_cv": domain_cv_labels.get(best_dcv_id_str),
                    "decision": (f"saved (s1d={best_s1d} ≥ {threshold})" if has_domain
                                 else f"saved (s1={s1})"),
                })

            source = source_map.get(job.get("source", "rss"), JobSource.rss)
            market = await detect_market_from_job(job.get("role", ""), job.get("company", ""), job.get("location", ""))

            # JD text — strip any stray HTML (RSS content / some Apify actors) before storing.
            jd_text = job.get("description") or ""
            if jd_text and "<" in jd_text:
                from bs4 import BeautifulSoup
                jd_text = BeautifulSoup(jd_text, "html.parser").get_text(separator="\n")
            jd_text = jd_text[:50000]

            session.add(Job(
                user_id=user.id,
                company=job.get("company", "Unknown"),
                role=job.get("role", "Unknown"),
                location=job.get("location"),
                market=market,
                jd_hash=job_hash,
                jd_raw=jd_text,
                jd_md=jd_text,
                portal_url=job.get("url"),
                source=source,
                status=JobStatus.new,
                s1=s1,
                s1d=best_s1d,
                domain_cv_scores=(dscores or None),
                best_domain_cv_id=(uuid.UUID(best_dcv_id_str) if best_dcv_id_str else None),
                salary_range_raw=job.get("salary"),
                source_feed_id=feed.id if feed else None,
                detected_domain_cv_id=feed.domain_cv_id if feed else None,
            ))
            added += 1
            if fid in stats:
                stats[fid]["saved"] += 1
        except Exception as e:
            print(f"⚠️ Failed to save job: {e}")
            continue

    await session.commit()
    print(f"✅ User {user.email}: {found} found, {added} added")
    return found, added, list(stats.values())

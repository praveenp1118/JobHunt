"""Phase 2 — Bright Data discovery source.

- client: normalizer + per-provider input builder (pure)
- scanner branch: pre-filter runs BEFORE any paid scoring (client + scorer mocked)
- dedup: a Bright Data LinkedIn job + an Apify one with the SAME job-id collapse to one row
- usage split: brightdata runs log provider='brightdata' (NOT lumped under apify), cost null
"""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.utils.brightdata_client import build_input, normalize_brightdata


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


# ── client: input builder (per-provider schema) ─────────────────────────────────
def test_build_input_linkedin_schema():
    d = build_input("linkedin", "Head of Product", "Amsterdam", "NL",
                    {"experience_level": "Executive", "time_range": "Past month"})
    assert d == {"keyword": "Head of Product", "location": "Amsterdam", "country": "NL",
                 "experience_level": "Executive", "time_range": "Past month"}


def test_build_input_indeed_schema():
    d = build_input("indeed", "Head of Product", "Amsterdam", "NL",
                    {"domain": "nl.indeed.com", "date_posted": "Last 7 days"})
    assert d == {"keyword_search": "Head of Product", "location": "Amsterdam", "country": "NL",
                 "domain": "nl.indeed.com", "date_posted": "Last 7 days"}


# ── client: normalizer (field mapping) ──────────────────────────────────────────
def test_normalize_brightdata_maps_fields():
    raw = {"job_title": "Head of Product", "company_name": "Acme",
           "job_location": "Amsterdam", "job_description_formatted": "<p>Lead product</p>",
           "url": "https://www.linkedin.com/jobs/view/123", "base_salary": "€150k",
           "job_posted_date": "2026-07-10", "job_seniority_level": "Executive"}
    n = normalize_brightdata(raw, "linkedin")
    assert n["role"] == "Head of Product" and n["company"] == "Acme"
    assert n["location"] == "Amsterdam" and n["url"].endswith("/jobs/view/123")
    assert n["description"].startswith("<p>") and n["salary"] == "€150k"
    assert n["seniority"] == "Executive"


def test_normalize_brightdata_drops_incomplete():
    assert normalize_brightdata({"job_title": "", "company_name": "X"}, "linkedin") is None
    assert normalize_brightdata({"job_title": "PM", "company_name": ""}, "indeed") is None


# ── scanner branch: pre-filter runs BEFORE paid scoring ─────────────────────────
async def test_brightdata_branch_prefilters_before_scoring(monkeypatch):
    """The Bright Data branch fetches+normalises, then the SHARED pipeline pre-filters
    (free) BEFORE scoring. A junk title (UNIVERSAL_SKIP) is dropped and NEVER reaches the
    Claude scorer; the valid title does — proving pre-filter precedes paid scoring."""
    import app.utils.brightdata_client as bd
    import app.agents.rag_scorer as rag
    from app.tasks.scanner_tasks import _scan_feeds_for_user

    async def fake_discover(**kwargs):
        return [
            {"job_title": "Head of Product", "company_name": "Acme",
             "url": "https://www.linkedin.com/jobs/view/111",
             "job_description_formatted": "Own the product roadmap. " * 20,
             "job_seniority_level": "Executive"},
            {"job_title": "Senior Software Engineer", "company_name": "Beta",
             "url": "https://www.linkedin.com/jobs/view/222",
             "job_description_formatted": "Backend platform work. " * 20,
             "job_seniority_level": "Mid-Senior level"},
        ]
    monkeypatch.setattr(bd, "brightdata_discover", fake_discover)

    scored_roles = []

    async def fake_rag(new_jobs, essence, cv_md, dcvs, config, key):
        scored_roles.extend(j.get("role") for j in new_jobs)   # what reached PAID scoring
        for j in new_jobs:                                     # reject → no DB write (fake user)
            j["_stage"] = "stage2_rejected"
            j["_reject_reason"] = "test"
        return {"jobs": new_jobs,
                "stats": {"total": len(new_jobs), "stage1_rejected": 0, "stage2_rejected": len(new_jobs),
                          "stage2_saved": 0, "stage3_scored": 0, "pending": 0, "tokens_stage2": 0,
                          "tokens_stage3": 0, "cost_inr": 0.0, "estimated_unoptimized_cost": 0.0,
                          "savings_pct": 0.0}}
    monkeypatch.setattr(rag, "hybrid_rag_score", fake_rag)

    from app.models.user import User
    eng, S = _sm()
    uid = uuid.uuid4()
    try:
        # Real user row so the brightdata usage-log insert satisfies its FK (as in prod).
        async with S() as s:
            s.add(User(id=uid, email=f"bdscan-{uid}@t.co", hashed_password="x", is_active=True,
                       is_superuser=False, is_verified=True, name="BDScan"))
            await s.commit()
        async with S() as session:
            user = SimpleNamespace(id=uid, email="bdscan@example.com")
            feed = SimpleNamespace(
                id=uuid.uuid4(), name="BD LinkedIn", feed_type="brightdata",
                url_or_actor="linkedin", provider_config={"country": "NL"},
                search_keywords="head of product", keywords=None,
                location="Amsterdam", actor_name=None, domain_cv_id=None)
            found, added, stats, _rag = await _scan_feeds_for_user(
                user, [feed], None, "fake-key", session, brightdata_token="bd-fake")

        assert found == 2                                   # both fetched + normalised
        assert scored_roles == ["Head of Product"]          # ONLY the valid one was scored
        assert "Senior Software Engineer" not in scored_roles   # junk dropped pre-scoring
        s = stats[0]
        assert s["feed_type"] == "brightdata" and s["raw_results"] == 2
        assert s["pre_filter_failed"] >= 1 and s["pre_filter_passed"] >= 1
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM api_usage_logs WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()


# ── dedup: Bright Data + Apify same LinkedIn id → one row ────────────────────────
async def test_brightdata_apify_same_linkedin_id_collapses():
    from app.utils.dedup import upsert_job, build_dedup_key
    from app.utils.brightdata_client import normalize_brightdata
    from app.mcp.apify_mcp import normalise_job
    from app.models.job import Job, JobSource, JobStatus
    from app.models.user import User

    eng, S = _sm()
    async with eng.connect() as c:
        has_idx = (await c.execute(text(
            "SELECT 1 FROM pg_indexes WHERE indexname='uq_jobs_user_dedup'"))).first()
    if not has_idx:
        await eng.dispose()
        import pytest
        pytest.skip("uq_jobs_user_dedup not applied yet")

    # Same LinkedIn posting (id 4432636617) as seen by Bright Data vs Apify — different
    # field formatting, but the canonical URL id makes the dedup_key identical.
    bd = normalize_brightdata({"job_title": "Head of Product", "company_name": "Booking.com",
                               "job_location": "Amsterdam",
                               "url": "https://www.linkedin.com/jobs/view/4432636617"}, "linkedin")
    apy = normalise_job({"title": "Head of Product - AI", "companyName": "Booking",
                         "location": "Amsterdam, NL", "descriptionText": "…",
                         "link": "https://www.linkedin.com/comm/jobs/view/4432636617/?trk=eml"},
                        "curious_coder/linkedin-jobs-scraper")
    k_bd = build_dedup_key(bd["company"], bd["role"], bd["location"], bd["url"])
    k_apy = build_dedup_key(apy["company"], apy["role"], apy["location"], apy["url"])
    assert k_bd == k_apy == "linkedin:4432636617"

    uid = uuid.uuid4()
    try:
        async with S() as s:
            s.add(User(id=uid, email=f"bd-{uid}@t.co", hashed_password="x", is_active=True,
                       is_superuser=False, is_verified=True, name="BD"))
            await s.commit()
        async with S() as s:
            _j, c1 = await upsert_job(s, dict(user_id=uid, company=bd["company"], role=bd["role"],
                location=bd["location"], portal_url=bd["url"], dedup_key=k_bd,
                source=JobSource.brightdata, status=JobStatus.new, jd_raw="x"))
            await s.commit()
        async with S() as s:
            _j2, c2 = await upsert_job(s, dict(user_id=uid, company=apy["company"], role=apy["role"],
                location=apy["location"], portal_url=apy["url"], dedup_key=k_apy,
                source=JobSource.apify, status=JobStatus.new, jd_raw="y"))
            await s.commit()
        assert c1 is True and c2 is False                    # Apify insert collapsed onto BD's row
        async with S() as s:
            n = (await s.execute(select(func.count()).select_from(Job).where(Job.user_id == uid))).scalar()
        assert n == 1
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()


# ── usage split: provider='brightdata', cost null ───────────────────────────────
async def test_brightdata_usage_logs_separate_provider():
    from app.utils.usage_logger import log_brightdata_usage
    from app.models.usage import APIUsageLog
    from app.models.user import User

    eng, S = _sm()
    uid = uuid.uuid4()
    try:
        async with S() as s:
            s.add(User(id=uid, email=f"bdu-{uid}@t.co", hashed_password="x", is_active=True,
                       is_superuser=False, is_verified=True, name="BDU"))
            await s.commit()
        async with S() as s:
            await log_brightdata_usage(s, uid, sub_source="linkedin", feed_label="BD LinkedIn",
                                       runs_requested=25, runs_returned=20, jobs_saved=7)
            await s.commit()
        async with S() as s:
            row = (await s.execute(select(APIUsageLog).where(APIUsageLog.user_id == uid))).scalars().first()
        assert row.provider == "brightdata"          # NOT 'apify'
        assert row.actor_id == "brightdata:linkedin"
        assert row.runs_returned == 20 and row.jobs_saved == 7
        assert row.estimated_cost_usd is None and row.estimated_cost_inr is None   # cost null
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM api_usage_logs WHERE user_id=:u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 — on-demand JD-by-URL enrichment (collect-by-URL)
# ══════════════════════════════════════════════════════════════════════════════
def test_canonicalize_job_url_matches_dedup():
    """Bright Data canonicalization uses the SAME job-id extraction as the dedup builder."""
    from app.utils.brightdata_client import canonicalize_job_url, detect_sub_source
    from app.utils.dedup import build_dedup_key
    li = "https://www.linkedin.com/comm/jobs/view/4432636617/?trackingId=abc&trk=eml"
    assert canonicalize_job_url(li, "linkedin") == "https://www.linkedin.com/jobs/view/4432636617"
    assert build_dedup_key("", "", "", li) == "linkedin:4432636617"   # identical id logic
    assert detect_sub_source(li) == "linkedin"
    ind = "https://nl.indeed.com/viewjob?jk=b661bc2362cab0c6"
    assert canonicalize_job_url(ind, "indeed") == "https://www.indeed.com/viewjob?jk=b661bc2362cab0c6"
    assert detect_sub_source(ind) == "indeed"
    assert detect_sub_source("https://boards.greenhouse.io/x/jobs/9") is None


async def test_collect_resolves_single_jsonl_record():
    """collect-by-URL returns ONE JSONL record (dict) synchronously → resolver → [rec]."""
    import json
    from app.utils.brightdata_client import _resolve_records
    rec = {"job_title": "Head of Product", "job_description_formatted": "x" * 500}
    r = SimpleNamespace(text=json.dumps(rec), status_code=200)
    out = await _resolve_records(None, r, "tok")
    assert out == [rec]


async def _seed_partial_job(S, *, with_token, uid, jid):
    from app.models.job import Job, JobSource, JobStatus
    from app.models.user import User, UserCredentials
    from app.utils.encryption import encrypt
    async with S() as s:   # commit the user (+creds) FIRST so the job FK resolves
        s.add(User(id=uid, email=f"e-{uid}@t.co", hashed_password="x", is_active=True,
                   is_superuser=False, is_verified=True, name="E"))
        if with_token:
            s.add(UserCredentials(user_id=uid, brightdata_token_enc=encrypt("bd-fake")))
        await s.commit()
    async with S() as s:
        s.add(Job(id=jid, user_id=uid, company="Acme", role="Head of Product",
                  portal_url="https://www.linkedin.com/comm/jobs/view/4432636617/?trk=eml",
                  has_partial_jd=True, source=JobSource.gmail_alert, status=JobStatus.new,
                  dedup_key="linkedin:4432636617"))
        await s.commit()


async def _cleanup(S, uid):
    async with S() as s:
        await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM user_credentials WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
        await s.commit()


async def test_enrich_brightdata_flips_partial(monkeypatch):
    """Happy path: BD returns the full JD → has_partial_jd flips false + rescore queued.
    Reuses the exact add-full-jd tail (score_pasted_jd → rescore_partial_job_from_text)."""
    from app.routers.jobs import enrich_brightdata
    from app.models.job import Job
    from app.models.user import User
    import app.utils.brightdata_client as bd
    import app.tasks.gmail_tasks as gt

    async def fake_collect(url, sub_source, token, **k):
        assert sub_source == "linkedin"
        return {"job_description_formatted": "Full JD. " * 60}
    monkeypatch.setattr(bd, "brightdata_collect_by_url", fake_collect)
    called = {}
    monkeypatch.setattr(gt.score_pasted_jd, "delay", lambda *a: called.setdefault("delay", a))

    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        await _seed_partial_job(S, with_token=True, uid=uid, jid=jid)
        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            res = await enrich_brightdata(jid, user, s)
        assert res["enriched"] is True and "delay" in called
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.has_partial_jd is False and (j.jd_raw or "").startswith("Full JD")
    finally:
        await _cleanup(S, uid)
        await eng.dispose()


async def test_enrich_brightdata_no_token_503():
    """No Bright Data token → clear 503; the job stays partial (paste fallback intact)."""
    import pytest
    from fastapi import HTTPException
    from app.routers.jobs import enrich_brightdata
    from app.models.job import Job
    from app.models.user import User

    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        await _seed_partial_job(S, with_token=False, uid=uid, jid=jid)
        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            with pytest.raises(HTTPException) as ei:
                await enrich_brightdata(jid, user, s)
        assert ei.value.status_code == 503
        assert ei.value.detail["code"] == "brightdata_token_required"
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.has_partial_jd is True
    finally:
        await _cleanup(S, uid)
        await eng.dispose()


async def test_enrich_brightdata_failure_keeps_partial(monkeypatch):
    """A Bright Data failure → 502 + the job STAYS partial so manual paste still works."""
    import pytest
    from fastapi import HTTPException
    from app.routers.jobs import enrich_brightdata
    from app.models.job import Job
    from app.models.user import User
    import app.utils.brightdata_client as bd
    from app.utils.brightdata_client import BrightDataError

    async def boom(*a, **k):
        raise BrightDataError("login wall")
    monkeypatch.setattr(bd, "brightdata_collect_by_url", boom)

    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        await _seed_partial_job(S, with_token=True, uid=uid, jid=jid)
        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            with pytest.raises(HTTPException) as ei:
                await enrich_brightdata(jid, user, s)
        assert ei.value.status_code == 502
        assert ei.value.detail["code"] == "brightdata_failed"
        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.has_partial_jd is True and not j.jd_raw   # unchanged; paste still available
    finally:
        await _cleanup(S, uid)
        await eng.dispose()

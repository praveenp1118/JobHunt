"""ATS + Pursuit dual scoring."""
import json
import types
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.ats_scorer import compute_ats_score
from app.agents.pursuit_scorer import compute_pursuit_score
from app.agents.dual_scorer import compute_dual_scores


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def _patch(monkeypatch, response_text):
    """Patch anthropic.Anthropic to return a fixed JSON payload; silence usage logging."""
    class _Msg:
        content = [type("C", (), {"text": response_text})()]
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()
    class _Messages:
        def create(self, **kw):
            return _Msg()
    class _Anthropic:
        def __init__(self, *a, **k):
            self.messages = _Messages()
    monkeypatch.setattr("anthropic.Anthropic", _Anthropic)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr("app.agents.ats_scorer.log_call", _noop)
    monkeypatch.setattr("app.agents.pursuit_scorer.log_call", _noop)


_ATS_5 = json.dumps({"components": {
    "keyword_density": {"score": 25}, "required_skills": {"score": 20},
    "experience_years": {"score": 18}, "seniority_alignment": {"score": 12},
    "education": {"score": 8}}, "total": 83, "dealbreaker_applied": False, "top_gap": "x"})
_ATS_DEAL = json.dumps({"components": {"required_skills": {"score": 0, "dealbreaker": "no Dutch"}},
                        "total": 40, "dealbreaker_applied": True, "top_gap": "Dutch fluency"})
_PURSUIT_4 = json.dumps({"components": {
    "human_excitement": {"score": 34}, "career_move_quality": {"score": 20},
    "achievability": {"score": 15}, "effort_reward": {"score": 12}},
    "total": 81, "recommendation": "Apply now"})
_GENERIC = json.dumps({"components": {"a": {"score": 1}}, "total": 80,
                       "recommendation": "Apply now", "top_gap": "x"})


# ── ATS scorer ──
async def test_ats_score_returns_5_components(monkeypatch):
    _patch(monkeypatch, _ATS_5)
    r = await compute_ats_score({"keywords": ["pm"]}, "JD text", anthropic_key="k")
    assert set(r["components"].keys()) == {
        "keyword_density", "required_skills", "experience_years", "seniority_alignment", "education"}
    assert r["total"] == 83


async def test_ats_score_applies_dealbreaker_cap(monkeypatch):
    _patch(monkeypatch, _ATS_DEAL)
    r = await compute_ats_score({"keywords": ["pm"]}, "must speak Dutch", anthropic_key="k")
    assert r["dealbreaker_applied"] is True and r["total"] <= 40


# ── Pursuit scorer ──
async def test_pursuit_score_returns_4_components(monkeypatch):
    _patch(monkeypatch, _PURSUIT_4)
    r = await compute_pursuit_score({"keywords": ["pm"]}, "cv md", "JD text", anthropic_key="k")
    assert set(r["components"].keys()) == {
        "human_excitement", "career_move_quality", "achievability", "effort_reward"}
    assert r["total"] == 81 and r["recommendation"] == "Apply now"


# ── Dual runner ──
async def test_dual_scores_runs_parallel(monkeypatch):
    _patch(monkeypatch, _GENERIC)
    r = await compute_dual_scores({"keywords": ["pm"]}, "cv md", "JD", "master", anthropic_key="k")
    assert r["ats"]["total"] == 80 and r["pursuit"]["total"] == 80 and r["cv_entity"] == "master"


async def test_dual_scores_saves_to_job(monkeypatch):
    _patch(monkeypatch, _GENERIC)
    job = types.SimpleNamespace(score_components=None)
    await compute_dual_scores({"keywords": ["pm"]}, "cv md", "JD", "master", job=job, anthropic_key="k")
    assert job.ats_master == 80 and job.pursuit_master == 80
    assert job.score_components["master"]["ats"]["total"] == 80


async def test_dual_scores_sets_domain_and_tailored_entities(monkeypatch):
    _patch(monkeypatch, _GENERIC)
    job = types.SimpleNamespace(score_components=None)
    await compute_dual_scores({}, "cv", "JD", "domain", job=job, anthropic_key="k")
    await compute_dual_scores({}, "cv", "JD", "tailored", job=job, anthropic_key="k")
    assert job.ats_domain == 80 and job.pursuit_tailored == 80
    assert "domain" in job.score_components and "tailored" in job.score_components


# ── Preferences ──
async def test_score_toggle_preference_saved(client, user_creds):
    await client.patch("/api/auth/me/preferences", json={"default_score_view": "ats"},
                       headers=user_creds["headers"])
    prefs = (await client.get("/api/auth/me/preferences", headers=user_creds["headers"])).json()
    assert prefs["default_score_view"] == "ats"


# ── API: graceful nulls + endpoints ──
async def test_null_scores_render_gracefully(client, user_creds):
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    try:
        uid = uuid.UUID((await client.get("/api/auth/me", headers=user_creds["headers"])).json()["id"])
        jid = uuid.uuid4()
        async with S() as s:
            s.add(Job(id=jid, user_id=uid, company="ZZ", role="PM", market="NL",
                      source=JobSource.manual, status=JobStatus.new, jd_raw="x"))
            await s.commit()
        r = await client.get("/api/jobs?limit=200", headers=user_creds["headers"])
        job = next((j for j in r.json()["jobs"] if j["id"] == str(jid)), None)
        assert job is not None and job["ats_master"] is None and job["pursuit_master"] is None
        sc = await client.get(f"/api/jobs/{jid}/scores", headers=user_creds["headers"])
        assert sc.status_code == 200 and sc.json()["totals"]["master"]["ats"] is None
    finally:
        await eng.dispose()


async def test_backfill_endpoint_estimates_cost(client, active_user_creds):
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    try:
        uid = uuid.UUID((await client.get("/api/auth/me", headers=active_user_creds["headers"])).json()["id"])
        async with S() as s:
            s.add(Job(id=uuid.uuid4(), user_id=uid, company="ZZ", role="PM", market="NL",
                      source=JobSource.manual, status=JobStatus.new, jd_raw="a real jd here"))
            await s.commit()
        r = await client.post("/api/jobs/backfill-scores", headers=active_user_creds["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["jobs"] >= 1 and body["estimated_cost_inr"] > 0
    finally:
        await eng.dispose()


async def test_stats_expose_recommendation_buckets(client, user_creds):
    r = await client.get("/api/jobs/stats", headers=user_creds["headers"])
    body = r.json()
    assert "apply_now_count" in body and "get_referral_count" in body and "skip_count" in body


# ── Filter / sort by ATS vs Pursuit ──
async def _mk_scored_jobs(client, user_creds):
    """Two jobs with opposite ATS/Pursuit so the score_field selection is testable:
    A = ats 85 / pursuit 50 · B = ats 50 / pursuit 85."""
    from app.models.job import Job, JobSource, JobStatus
    uid = uuid.UUID((await client.get("/api/auth/me", headers=user_creds["headers"])).json()["id"])
    a, b = uuid.uuid4(), uuid.uuid4()
    eng, S = _sm()
    async with S() as s:
        s.add(Job(id=a, user_id=uid, company="AA", role="PM", market="NL",
                  source=JobSource.manual, status=JobStatus.new, jd_raw="x", ats_master=85, pursuit_master=50))
        s.add(Job(id=b, user_id=uid, company="BB", role="PM", market="NL",
                  source=JobSource.manual, status=JobStatus.new, jd_raw="x", ats_master=50, pursuit_master=85))
        await s.commit()
    await eng.dispose()
    return str(a), str(b)


async def test_tracker_filters_by_pursuit_when_toggle_pursuit(client, user_creds):
    a, b = await _mk_scored_jobs(client, user_creds)
    r = await client.get("/api/jobs?limit=200&score=70&score_field=pursuit_master", headers=user_creds["headers"])
    ids = {j["id"] for j in r.json()["jobs"]}
    assert b in ids and a not in ids  # only the high-Pursuit job


async def test_tracker_filters_by_ats_when_toggle_ats(client, user_creds):
    a, b = await _mk_scored_jobs(client, user_creds)
    r = await client.get("/api/jobs?limit=200&score=70&score_field=ats_master", headers=user_creds["headers"])
    ids = {j["id"] for j in r.json()["jobs"]}
    assert a in ids and b not in ids  # only the high-ATS job


async def test_stats_returns_filtered_avg_scores(client, user_creds):
    await _mk_scored_jobs(client, user_creds)
    body = (await client.get("/api/jobs/stats", headers=user_creds["headers"])).json()
    assert body["avg_ats_master"] is not None and body["avg_pursuit_master"] is not None


async def test_feeds_performance_returns_avg_ats_pursuit(client, user_creds):
    from app.models.job import Job, JobSource, JobStatus
    from app.models.domain import UserFeed
    uid = uuid.UUID((await client.get("/api/auth/me", headers=user_creds["headers"])).json()["id"])
    fid = uuid.uuid4()
    eng, S = _sm()
    try:
        async with S() as s:
            s.add(UserFeed(id=fid, user_id=uid, feed_type="rss", name="T", url_or_actor="http://x", is_active=True))
            await s.flush()
            s.add(Job(id=uuid.uuid4(), user_id=uid, company="AA", role="PM", market="NL",
                      source=JobSource.rss, status=JobStatus.new, jd_raw="x",
                      source_feed_id=fid, ats_master=80, pursuit_master=75))
            await s.commit()
        rows = (await client.get("/api/feeds/performance", headers=user_creds["headers"])).json()
        row = next((r for r in rows if r.get("feed_id") == str(fid)), None)
        assert row is not None and row["avg_ats_master"] == 80 and row["avg_pursuit_master"] == 75
    finally:
        await eng.dispose()


async def test_auto_dual_score_pref_gates_scan_scoring(client, user_creds):
    # Default off; settable via preferences (the scanner reads this flag to gate dual scoring).
    prefs = (await client.get("/api/auth/me/preferences", headers=user_creds["headers"])).json()
    assert prefs.get("auto_dual_score_on_scan") in (False, None)
    await client.patch("/api/auth/me/preferences", json={"auto_dual_score_on_scan": True},
                       headers=user_creds["headers"])
    prefs2 = (await client.get("/api/auth/me/preferences", headers=user_creds["headers"])).json()
    assert prefs2["auto_dual_score_on_scan"] is True


async def test_score_view_loaded_from_preferences(client, user_creds):
    # GET /preferences exposes the display fields the Tracker loads its toggle from.
    prefs = (await client.get("/api/auth/me/preferences", headers=user_creds["headers"])).json()
    assert prefs.get("default_score_view") in ("pursuit", "ats", "combined")
    assert prefs.get("score_pill_style") in ("dual_ring", "single", "number_only")

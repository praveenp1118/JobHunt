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


# ── Backfill DOMAIN pass (Best Fit) ──
async def test_backfill_domain_pass_fills_best_fit(monkeypatch):
    """ats_domain NULL + active domain CV → backfill sets ats_domain/pursuit_domain +
    best_domain_cv_id. Master pass untouched (ats_master already set)."""
    import app.agents.dual_scorer as dual_mod
    import app.agents.scanner_agents as sa_mod
    from app.tasks.scoring_tasks import _backfill_async
    from app.models.user import User, UserCredentials
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.job import Job, JobSource, JobStatus
    from app.models.domain import IndustryVertical, FunctionalDiscipline
    from app.utils.encryption import encrypt

    async def fake_batch(cv_md, jobs, batch_size=5, api_key=None, model=None):
        return [{"id": j["id"], "s1_score": 80, "key_matches": [], "gaps": []} for j in jobs]

    async def fake_dual(cv_essence, cv_md, jd_text, cv_entity, job=None,
                        anthropic_key=None, session=None, **kw):
        if job is not None:
            setattr(job, f"ats_{cv_entity}", 70.0)
            setattr(job, f"pursuit_{cv_entity}", 66.0)
            comps = dict(job.score_components or {})
            comps[cv_entity] = {"ats": {"total": 70.0}, "pursuit": {"total": 66.0}}
            job.score_components = comps
            if session is not None:
                await session.commit()
        return {"ats": {"total": 70.0}, "pursuit": {"total": 66.0}, "cv_entity": cv_entity}

    monkeypatch.setattr(sa_mod, "batch_score_s1", fake_batch)
    monkeypatch.setattr(dual_mod, "compute_dual_scores", fake_dual)

    eng, S = _sm()
    uid, jid, dcv_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with S() as s:
            ind = (await s.execute(select(IndustryVertical.id).limit(1))).scalar()
            fn = (await s.execute(select(FunctionalDiscipline.id).limit(1))).scalar()
            if not ind or not fn:
                return  # seed data absent (fresh DB) — skip cleanly
            s.add(User(id=uid, email=f"bf-{uid}@t.co", hashed_password="x",
                       is_active=True, is_superuser=False, is_verified=True, name="BF"))
            await s.flush()
            s.add(UserCredentials(user_id=uid, anthropic_api_key_enc=encrypt("sk-fake")))
            mcv = MasterCV(id=uuid.uuid4(), user_id=uid, content_md="MASTER", word_count=100,
                           essence_json={"keywords": ["product"]}, is_active=True, version=1)
            s.add(mcv)
            await s.flush()
            s.add(DomainCV(id=dcv_id, user_id=uid, master_cv_id=mcv.id, industry_id=ind,
                           function_id=fn, country_code="NL", content_md="DOMAIN CV",
                           essence_json={"keywords": ["ai"]}, status=CVStatus.active, version=1))
            s.add(Job(id=jid, user_id=uid, company="Acme", role="Head of Product", market="NL",
                      source=JobSource.rss, status=JobStatus.new, jd_raw="JD text " * 30,
                      jd_md="JD text " * 30, ats_master=72.0, pursuit_master=68.0))
            await s.commit()

        # _backfill_async uses the module engine; dispose its pool so it binds to THIS
        # test's event loop (the Celery wrapper normally does this; a direct call must).
        from app.database import engine as _mod_engine
        await _mod_engine.dispose()
        await _backfill_async(str(uid))

        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.ats_domain == 70.0 and j.pursuit_domain == 66.0
            assert str(j.best_domain_cv_id) == str(dcv_id)
            assert j.ats_master == 72.0  # master pass untouched
    finally:
        from app.database import engine as _mod_engine
        await _mod_engine.dispose()
        async with S() as s:
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})  # CASCADE
            await s.commit()
        await eng.dispose()


async def test_backfill_domain_pass_noop_without_domain_cv(monkeypatch):
    """No active domain CV → domain pass is a clean no-op (ats_domain stays NULL, no error)."""
    import app.agents.dual_scorer as dual_mod
    import app.agents.scanner_agents as sa_mod
    from app.tasks.scoring_tasks import _backfill_async
    from app.models.user import User, UserCredentials
    from app.models.cv import MasterCV
    from app.models.job import Job, JobSource, JobStatus
    from app.utils.encryption import encrypt

    async def fake_batch(*a, **k):
        return []
    async def fake_dual(*a, **k):
        return {"ats": {}, "pursuit": {}, "cv_entity": None}
    monkeypatch.setattr(sa_mod, "batch_score_s1", fake_batch)
    monkeypatch.setattr(dual_mod, "compute_dual_scores", fake_dual)

    eng, S = _sm()
    uid, jid = uuid.uuid4(), uuid.uuid4()
    try:
        async with S() as s:
            s.add(User(id=uid, email=f"bf2-{uid}@t.co", hashed_password="x",
                       is_active=True, is_superuser=False, is_verified=True, name="BF2"))
            await s.flush()
            s.add(UserCredentials(user_id=uid, anthropic_api_key_enc=encrypt("sk-fake")))
            s.add(MasterCV(id=uuid.uuid4(), user_id=uid, content_md="M", word_count=10,
                           essence_json={"keywords": ["x"]}, is_active=True, version=1))
            s.add(Job(id=jid, user_id=uid, company="Acme", role="PM", market="NL",
                      source=JobSource.rss, status=JobStatus.new, jd_raw="JD " * 40, ats_master=50.0))
            await s.commit()

        from app.database import engine as _mod_engine
        await _mod_engine.dispose()
        await _backfill_async(str(uid))  # must not raise

        async with S() as s:
            j = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert j.ats_domain is None    # domain pass no-op'd cleanly
    finally:
        from app.database import engine as _mod_engine
        await _mod_engine.dispose()
        async with S() as s:
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()

"""Hybrid-RAG scoring tests — essence schema, 3-stage routing, presets, estimate endpoint."""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.essence_agent import CV_ESSENCE_SCHEMA
from app.agents.rag_scorer import SCORING_PRESETS, config_from_prefs, hybrid_rag_score, estimate_scan_cost

ESSENCE = {"keywords": ["python", "product", "ai"], "core_identity": "PM", "years_experience": 10}
BAL = dict(SCORING_PRESETS["balanced"])


class FakeScorer:
    """Stand-in for batch_score_s1 — returns a fixed score, records (model, n) per call."""
    def __init__(self, score):
        self.score = score
        self.calls = []

    async def __call__(self, cv_text, jobs, batch_size=5, api_key=None, model=None):
        self.calls.append({"model": model, "n": len(jobs)})
        return [{"id": j["id"], "s1_score": self.score, "key_matches": [], "gaps": []} for j in jobs]


def _job(desc, hash_):
    return {"role": "Head of Product", "company": "X", "location": "NL", "description": desc, "jd_hash": hash_}


# ── Pure ──
def test_extract_cv_essence_returns_schema():
    for k in ["keywords", "core_identity", "top_experiences", "domain_strengths",
              "seniority_level", "markets", "education", "certifications", "years_experience"]:
        assert k in CV_ESSENCE_SCHEMA


def test_preset_balanced_sets_correct_config():
    b = SCORING_PRESETS["balanced"]
    assert b["s1_essence_model"] == "claude-haiku-4-5"
    assert b["s1_full_model"] == "claude-sonnet-4-6"
    assert b["keyword_match_threshold"] == 3 and b["s1_borderline_high"] == 74


def test_preset_maximum_quality_config():
    q = SCORING_PRESETS["maximum_quality"]
    assert q["s1_essence_model"] == "claude-sonnet-4-6" and q["s1_full_model"] == "claude-sonnet-4-6"
    assert q["keyword_match_threshold"] == 2


def test_preset_maximum_savings_config():
    s = SCORING_PRESETS["maximum_savings"]
    assert s["s1_full_model"] == "claude-haiku-4-5" and s["keyword_match_threshold"] == 5


def test_cost_estimate_helper():
    e = estimate_scan_cost(BAL, 300, 3)
    assert e["estimated_total_jobs"] == 300 and e["estimated_cost_inr"] > 0
    assert e["savings_pct"] > 0


# ── Pipeline routing (monkeypatched scorer — no real Claude) ──
async def test_stage1_rejects_below_threshold(monkeypatch):
    fake = FakeScorer(80)
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", fake)
    jobs = [_job("sales finance operations role", "h1")]  # 0 keyword matches
    r = await hybrid_rag_score(jobs, ESSENCE, "MASTER", [], BAL, "key")
    assert r["stats"]["stage1_rejected"] == 1
    assert jobs[0]["_stage"] == "stage1_rejected"
    assert fake.calls == []  # no model call for a Stage-1 rejection


async def test_stage1_passes_above_threshold(monkeypatch):
    fake = FakeScorer(80)
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", fake)
    jobs = [_job("python product ai leadership", "h2")]  # 3 matches ≥ threshold 3
    r = await hybrid_rag_score(jobs, ESSENCE, "MASTER", [], BAL, "key")
    assert r["stats"]["stage1_rejected"] == 0
    assert jobs[0].get("_s1_essence") == 80


async def test_stage2_uses_haiku_model(monkeypatch):
    fake = FakeScorer(60)
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", fake)
    jobs = [_job("python product ai", "h3")]
    await hybrid_rag_score(jobs, ESSENCE, "MASTER", [], BAL, "key")
    assert fake.calls[0]["model"] == "claude-haiku-4-5"  # Stage 2 = essence model


async def test_stage3_uses_sonnet_for_borderline(monkeypatch):
    fake = FakeScorer(60)  # in borderline 50-74 → needs full-CV scoring
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", fake)
    jobs = [_job("python product ai", "h4")]
    r = await hybrid_rag_score(jobs, ESSENCE, "MASTER", [], BAL, "key")
    assert r["stats"]["stage3_scored"] == 1
    assert any(c["model"] == "claude-sonnet-4-6" for c in fake.calls)  # Stage 3 = full model


async def test_confident_save_skips_stage3(monkeypatch):
    fake = FakeScorer(90)  # ≥ borderline_high 74 → confident save at Stage 2
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", fake)
    jobs = [_job("python product ai", "h5")]
    r = await hybrid_rag_score(jobs, ESSENCE, "MASTER", [], BAL, "key")
    assert r["stats"]["stage3_scored"] == 0
    assert jobs[0]["_stage"] == "stage2_saved" and jobs[0]["s1"] == 90


async def test_domain_scoring_skipped_below_min_s1(monkeypatch):
    fake = FakeScorer(50)  # below domain_score_min_s1 (55)
    monkeypatch.setattr("app.agents.scanner_agents.batch_score_s1", fake)
    jobs = [_job("python product ai", "h6")]
    domain_cvs = [{"id": "dcv1", "content_md": "DOMAIN", "essence": None}]
    await hybrid_rag_score(jobs, ESSENCE, "MASTER", domain_cvs, BAL, "key")
    assert jobs[0].get("s1d") is None and jobs[0].get("domain_cv_scores") is None


# ── Config + endpoint ──
def test_config_from_prefs_defaults_to_balanced():
    c = config_from_prefs(None)
    assert c["s1_essence_model"] == "claude-haiku-4-5" and c["keyword_match_threshold"] == 3


async def test_cost_estimate_endpoint_returns_data(client, user_creds):
    r = await client.get("/api/scoring/estimate", headers=user_creds["headers"])
    assert r.status_code == 200
    d = r.json()
    assert "estimated_cost_inr" in d and "unoptimized_cost_inr" in d and "savings_pct" in d


async def test_essence_stored_on_master_cv(user_creds, client):
    """The essence_json column round-trips on master_cvs (migration applied)."""
    eng = create_async_engine(settings.database_url)
    Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        me = (await client.get("/api/auth/me", headers=user_creds["headers"])).json()
        uid = me["id"]
        from app.models.cv import MasterCV
        async with Session() as s:
            cv = MasterCV(user_id=uuid.UUID(uid), content_md="# CV", version=1,
                          essence_json={"keywords": ["a", "b"]}, essence_version=1)
            s.add(cv)
            await s.commit()
            got = (await s.execute(select(MasterCV).where(MasterCV.user_id == uuid.UUID(uid)))).scalars().first()
            assert got.essence_json["keywords"] == ["a", "b"]
            await s.execute(text("delete from master_cvs where user_id = :u"), {"u": uid})
            await s.commit()
    finally:
        await eng.dispose()

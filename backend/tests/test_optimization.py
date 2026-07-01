"""RAG + tiered-model optimization across Claude calls."""
import hashlib
import inspect
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.agents.gmail_agents import rule_classify
from app.agents.tailor_agents import JD_HIGHLIGHTS_MODEL, extract_jd_highlights
from app.agents.feed_agents import FEED_KEYWORDS_MODEL, generate_feed_keywords
from app.agents import gmail_alert_agent


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


# ── Group 2: email rule classifier (free tier) ──
def test_email_rule_classify_rejection():
    assert rule_classify("Update on your application",
                         "Unfortunately we are moving forward with other candidates") == "auto_rejection"


def test_email_rule_classify_interview():
    assert rule_classify("Next steps", "We would like to schedule a call with you") == "interview_invite"


def test_email_rule_classify_returns_none_for_unclear():
    assert rule_classify("Coffee tomorrow?", "Want to grab a coffee and catch up?") is None


# ── Group 4: JD highlights — Haiku + cache ──
def test_jd_highlights_uses_haiku():
    assert JD_HIGHLIGHTS_MODEL == "claude-haiku-4-5"


async def test_jd_highlights_uses_haiku_call(monkeypatch):
    captured = {}

    class _Msg:
        def __init__(self):
            self.content = [type("C", (), {"text": '{"matches":["x"],"gaps":["y"]}'})()]
            self.usage = type("U", (), {"input_tokens": 5, "output_tokens": 3})()

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                captured["model"] = kw.get("model")
                return _Msg()

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr("app.agents.tailor_agents._get_client", lambda *a, **k: _Client())
    monkeypatch.setattr("app.agents.tailor_agents.log_call", _noop)
    out = await extract_jd_highlights("A sufficiently long job description text. " * 5)
    assert captured["model"] == "claude-haiku-4-5"
    assert out["matches"] == ["x"]


async def test_jd_highlights_cached_on_second_call(client, active_user_creds):
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    try:
        uid = uuid.UUID((await client.get("/api/auth/me", headers=active_user_creds["headers"])).json()["id"])
        jd = "Head of Product role. 8+ years leadership and API platform experience required. " * 3
        sig = hashlib.sha256(jd.encode("utf-8")).hexdigest()[:16]
        jid = uuid.uuid4()
        async with S() as s:
            s.add(Job(id=jid, user_id=uid, company="Acme", role="Head of Product", market="NL",
                      source=JobSource.manual, status=JobStatus.new, jd_raw=jd,
                      jd_highlights_json={"matches": ["cached-m"], "gaps": ["cached-g"], "_jd_sig": sig}))
            await s.commit()
        # Cache hit → returns stored highlights, no Claude call. (domain_cv_id is required by
        # the schema but only drives country_rules; a random one → no domain CV found → [].)
        r = await client.post("/api/tailor/jd-highlights",
                              json={"job_id": str(jid), "domain_cv_id": str(uuid.uuid4())},
                              headers=active_user_creds["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["cached"] is True and body["matches"] == ["cached-m"]
    finally:
        await eng.dispose()


# ── Group 5: feed keywords — Haiku ──
def test_feed_keywords_uses_haiku():
    assert FEED_KEYWORDS_MODEL == "claude-haiku-4-5"
    assert inspect.signature(generate_feed_keywords).parameters["model"].default == "claude-haiku-4-5"


# ── Group 1: gmail alert public path wires the full 3-stage pipeline ──
def test_gmail_alert_uses_full_rag_pipeline():
    src = inspect.getsource(gmail_alert_agent.process_job_alert_email)
    assert "config_from_prefs" in src
    assert "s1_essence_model" in src and "s1_borderline_low" in src and "s1_full_model" in src


# ── Group 3: manual parse — tiered RAG (Haiku essence → Sonnet only if borderline) ──
async def test_manual_parse_uses_rag_pipeline(monkeypatch):
    calls = []

    async def _fake_parse(raw, cv, key, model=None):
        calls.append(model)
        return {"parsed": {"company": "X", "role": "Y"}, "s1_score": 60, "key_matches": [], "gaps": []}

    monkeypatch.setattr("app.agents.jd_agents.parse_and_score_jd", _fake_parse)
    from app.agents.jd_agents import tiered_parse_and_score
    essence = {"keywords": ["product"], "core_identity": "Senior PM"}
    # Balanced preset: borderline 50–74 → a 60 essence score escalates to the full-CV model.
    res = await tiered_parse_and_score("jd text", "FULL CV TEXT", essence, None, "key")
    assert res["stage"] == "stage3_full"
    assert calls == ["claude-haiku-4-5", "claude-sonnet-4-6"]

"""V3 scanner breakdown — verify _scan_feeds_for_user produces the rich per-feed
stats that _weekly_scan_async stores under run_log.details['feeds_summary'].

Mocks the RSS fetch to empty so the test is deterministic with no network/Claude.
Uses a fresh engine + fake user/feed objects (no persistence needed — the master
CV / prefs / dedup queries just return nothing for a random user id)."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
import app.mcp.rss_mcp as rss_mod
from app.tasks.scanner_tasks import _scan_feeds_for_user

FEED_SUMMARY_KEYS = {
    "feed_name", "feed_type", "raw_results", "pre_filter_passed", "pre_filter_failed",
    "s1_scored", "above_threshold", "duplicates", "saved", "rejected", "note",
}


async def _empty_rss(url):
    return []


async def test_scanner_feeds_summary_breakdown():
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            user = SimpleNamespace(id=uuid.uuid4(), email="scantest@example.com")
            feed = SimpleNamespace(
                id=uuid.uuid4(), name="Indeed NL", feed_type="rss",
                url_or_actor="https://example.com/rss", search_keywords=None,
                keywords=None, location=None, actor_name=None, domain_cv_id=None,
            )
            with patch.object(rss_mod, "fetch_rss_feed", _empty_rss):
                found, added, stats, rag_stats = await _scan_feeds_for_user(user, [feed], None, None, session)

        assert found == 0 and added == 0
        assert len(stats) == 1
        s = stats[0]
        assert FEED_SUMMARY_KEYS.issubset(s.keys()), f"missing keys: {FEED_SUMMARY_KEYS - set(s.keys())}"
        assert s["feed_name"] == "Indeed NL"
        assert s["feed_type"] == "rss"
        assert s["note"] == "Feed returned no results"

        # This list is exactly what _weekly_scan_async stores under details.feeds_summary
        details = {"feeds_run": len(stats), "feeds_summary": stats}
        assert "feeds_summary" in details
        assert details["feeds_summary"][0]["feed_name"] == "Indeed NL"
    finally:
        await engine.dispose()


# ── Apify quota/credit-exhaustion hardening ──────────────────────────────────

def test_apify_quota_signal_classification():
    """Clear usage/credit signals classify as quota; ambiguous ones do NOT."""
    from app.mcp.apify_mcp import _is_quota_signal, _apify_error_body

    assert _is_quota_signal("monthly-usage-hard-limit-exceeded")
    assert _is_quota_signal("You have insufficient credit on your account")
    assert _is_quota_signal("Payment required")
    # Conservative: a network blip / access / token issue is NOT "out of credits".
    assert not _is_quota_signal("connection reset by peer")
    assert not _is_quota_signal("actor not found")
    assert not _is_quota_signal("invalid token")
    assert not _is_quota_signal("")

    class _Resp:
        def json(self):
            return {"error": {"type": "monthly-usage-hard-limit-exceeded", "message": "limit reached"}}
    body = _apify_error_body(_Resp())
    assert "monthly-usage-hard-limit-exceeded" in body and "limit reached" in body


def test_generic_apify_error_not_classified_as_quota():
    """Guard against mislabeling generic 403/timeout text as exhaustion."""
    from app.mcp.apify_mcp import _is_quota_signal
    for s in ("403 Forbidden", "Request timed out", "DNS failure", "Bad Gateway"):
        assert not _is_quota_signal(s)


def test_run_status_partial_on_feed_failure():
    """A quota/failed feed → summarize_feed_outcomes flags it → run status is partial."""
    from app.tasks.scanner_tasks import summarize_feed_outcomes
    stats = [
        {"feed_name": "LinkedIn NL", "error": True, "error_kind": "quota_exhausted"},
        {"feed_name": "Jobicy", "error": False, "error_kind": None},
        {"feed_name": "Google Jobs", "error": True, "error_kind": "failed"},
    ]
    failed, quota, other = summarize_feed_outcomes(stats)
    assert len(failed) == 2 and len(quota) == 1 and len(other) == 1
    assert quota[0]["feed_name"] == "LinkedIn NL"

    errors = []  # no user-level errors this run
    status_is_partial = bool(errors) or bool(failed)
    assert status_is_partial is True

    # And an all-clear run stays success.
    ok_failed, _q, _o = summarize_feed_outcomes(
        [{"feed_name": "Jobicy", "error": False}])
    assert not ok_failed


async def test_scan_feed_quota_skips_and_isolates_rss():
    """An Apify feed hitting quota is classified + skipped; the RSS feed in the same
    scan still runs (isolation); the whole scan does not raise."""
    import app.mcp.apify_mcp as apify_mod
    from app.mcp.apify_mcp import ApifyQuotaExhausted

    async def _fake_quota_run_actor(*a, **k):
        raise ApifyQuotaExhausted(
            "Apify usage/credit limit reached (monthly-usage-hard-limit-exceeded)",
            actor_id="user/linkedin-jobs-scraper")

    async def _one_rss(url):
        # SKIP_WORDS title → pre-filtered out (no DB write / no FK on the fake user),
        # but still counts as fetched, proving RSS ran independently of the Apify fail.
        return [{"role": "Senior Software Engineer", "company": "Acme",
                 "description": "backend platform role. " * 30}]

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            user = SimpleNamespace(id=uuid.uuid4(), email="quotatest@example.com")
            rss_feed = SimpleNamespace(
                id=uuid.uuid4(), name="Jobicy RSS", feed_type="rss",
                url_or_actor="https://example.com/rss", search_keywords=None,
                keywords=None, location=None, actor_name=None, domain_cv_id=None)
            apify_feed = SimpleNamespace(
                id=uuid.uuid4(), name="LinkedIn NL", feed_type="apify",
                url_or_actor="user/linkedin-jobs-scraper", actor_name="linkedin",
                search_keywords="head of product", keywords=None,
                location="Netherlands", domain_cv_id=None)
            with patch.object(rss_mod, "fetch_rss_feed", _one_rss), \
                 patch.object(apify_mod, "run_actor", _fake_quota_run_actor):
                found, added, stats, _rag = await _scan_feeds_for_user(
                    user, [rss_feed, apify_feed], "fake-token", None, session)

        by_name = {s["feed_name"]: s for s in stats}
        # Apify feed classified as quota-exhausted (skipped, not raised).
        apy = by_name["LinkedIn NL"]
        assert apy["error"] is True
        assert apy["error_kind"] == "quota_exhausted"
        assert "Apify" in (apy["note"] or "")
        # RSS feed still ran (isolation) — one raw result fetched.
        rss = by_name["Jobicy RSS"]
        assert rss["raw_results"] == 1
        assert not rss["error"]
        # Only the RSS job entered the pipeline; nothing saved (pre-filtered out).
        assert found == 1 and added == 0
    finally:
        await engine.dispose()


# ── S1 scoring robustness (truncation + id-mapping fix) ──────────────────────

def test_parse_scores_tolerates_truncation():
    """A truncated score array salvages every COMPLETE object and drops the cut one;
    code fences are stripped."""
    from app.agents.scanner_agents import _parse_scores

    # Clean fenced JSON.
    clean = _parse_scores('```json\n[{"id":"1","s1_score":88},{"id":"2","s1_score":72}]\n```')
    assert [e["s1_score"] for e in clean] == [88, 72]

    # Truncated tail (max_tokens cut mid-entry) — the 2 complete objects survive.
    truncated = _parse_scores('[{"id":"1","s1_score":88}, {"id":"2","s1_score":72}, {"id":"3","s1_sc')
    assert [str(e["id"]) for e in truncated] == ["1", "2"]
    assert [e["s1_score"] for e in truncated] == [88, 72]


async def test_batch_score_s1_retries_missing_no_blanket_zero(monkeypatch):
    """Simulate truncation: _score_once returns only the first half when >1 job.
    batch_score_s1 must re-score the rest (halving to singles) so ALL jobs get a
    real non-zero score keyed by their original 64-hex id — never a blanket zero."""
    import hashlib
    import app.agents.scanner_agents as sa

    async def fake_once(cv_md, jobs, api_key, model):
        # "Truncate": score only the first half of a multi-job batch; always score a single.
        take = jobs if len(jobs) == 1 else jobs[: (len(jobs) + 1) // 2]
        return {j["id"]: {"id": j["id"], "s1_score": 60 + (idx % 5) * 7,
                          "key_matches": [], "gaps": []}
                for idx, j in enumerate(take)}

    monkeypatch.setattr(sa, "_score_once", fake_once)

    ids = [hashlib.sha256(f"job-{i}".encode()).hexdigest() for i in range(6)]
    jobs = [{"id": ids[i], "role": f"PM {i}", "company": "Co", "description": "x" * 200}
            for i in range(6)]
    out = await sa.batch_score_s1("CV", jobs, batch_size=6, api_key="k", model="claude-haiku-4-5")

    assert len(out) == 6
    assert {r["id"] for r in out} == set(ids)          # keyed by the original 64-hex ids
    assert all(r["s1_score"] > 0 for r in out)          # nothing blanket-zeroed


async def test_score_once_maps_short_ids_back_to_hash(monkeypatch):
    """The model echoes short ids ("1".."n"); _score_once maps them back to the real
    64-hex job ids. Proves the model never needs to echo the opaque hash."""
    import hashlib
    from types import SimpleNamespace
    import app.agents.scanner_agents as sa

    h1 = hashlib.sha256(b"a").hexdigest()
    h2 = hashlib.sha256(b"b").hexdigest()
    fake_resp = SimpleNamespace(
        content=[SimpleNamespace(text='[{"id":"1","s1_score":88},{"id":"2","s1_score":72}]')],
        usage=SimpleNamespace(input_tokens=5, output_tokens=5), stop_reason="end_turn")
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: fake_resp))
    monkeypatch.setattr(sa, "_get_client", lambda api_key=None: fake_client)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(sa, "log_call", _noop)

    jobs = [{"id": h1, "role": "PM", "company": "A", "description": "d"},
            {"id": h2, "role": "PM", "company": "B", "description": "d"}]
    got = await sa._score_once("CV", jobs, "key", "claude-haiku-4-5")
    assert got[h1]["s1_score"] == 88.0
    assert got[h2]["s1_score"] == 72.0


def test_apify_redact_token():
    """Token material is scrubbed from any string before it can be logged."""
    from app.mcp.apify_mcp import _redact
    # Built by concatenation so no literal Apify token sits in source (this repo is
    # public + gitleaks-hooked). Low-entropy fake value, not a real credential.
    fake = "apify_api_" + "FAKEfake" * 4
    leaky = (f"Client error '403 Forbidden' for url "
             f"'https://api.apify.com/v2/acts/x~y/runs?token={fake}'")
    red = _redact(leaky)
    assert fake not in red
    assert "FAKEfakeFAKEfake" not in red
    assert "token=***" in red or "apify_api_***" in red


# ── Phase 2: non-product functional disciplines seeded ──────────────────────
def test_seed_has_non_product_functional_disciplines():
    from app.seeds import FUNCTIONAL_DISCIPLINES
    labels = {d["label"] for d in FUNCTIONAL_DISCIPLINES}
    for expected in ("Finance & FP&A", "Operations & Supply Chain", "Sales & Commercial",
                     "Strategy & Consulting", "Marketing & Growth"):
        assert expected in labels
    # product disciplines are still present, and every code is unique
    assert "AI & ML Product Management" in labels
    codes = [d["code"] for d in FUNCTIONAL_DISCIPLINES]
    assert len(codes) == len(set(codes)) and len(codes) >= 20

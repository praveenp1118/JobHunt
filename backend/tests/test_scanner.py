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

"""Redis-backed login lockout — 5 failed attempts per email → 15-minute lockout."""
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger("jobhunt.security")

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

_client = None


def _redis():
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


def _key(email: str) -> str:
    return f"login_attempts:{(email or '').strip().lower()}"


async def is_locked_out(email: str) -> bool:
    try:
        return int(await _redis().get(_key(email)) or 0) >= MAX_ATTEMPTS
    except Exception as e:  # noqa: BLE001 — Redis down must not block login
        logger.warning(f"login lockout check failed: {e}")
        return False


async def record_failure(email: str) -> int:
    """Increment the failure counter (15-min TTL). Returns the new count."""
    try:
        r = _redis()
        k = _key(email)
        n = await r.incr(k)
        await r.expire(k, LOCKOUT_SECONDS)
        return int(n)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"login failure record failed: {e}")
        return 0


async def clear_attempts(email: str):
    try:
        await _redis().delete(_key(email))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"login attempts clear failed: {e}")

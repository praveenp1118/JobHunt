"""
API usage logging — records every external API call (Anthropic message / Apify
actor run) to api_usage_logs for the Settings → API Usage tab.

Logging must NEVER block or break the main operation, so callers wrap these in
try/except (or use log_anthropic_usage_safe, which manages its own session).
"""
import uuid
import contextvars
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import APIUsageLog

# The current user for usage attribution. Set at the router/Celery-task boundary
# (set_usage_user) so deep agent calls can log without threading user_id through
# every signature. Copies into child tasks created by asyncio.gather/to_thread.
_current_user_id: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "usage_user_id", default=None)
# Per-request accumulators so endpoints can return tokens/cost at the point of action
# (no extra DB round-trip). Reset whenever the attribution user changes (i.e. new request).
_session_usage: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar(
    "usage_session", default=None)
_last_usage: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar(
    "usage_last", default=None)
_current_entity: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar(
    "usage_entity", default=None)


def reset_session_usage() -> None:
    _session_usage.set({"tokens": 0, "cost_inr": 0.0})
    _last_usage.set(None)


def set_usage_user(user_id) -> None:
    uid = str(user_id) if user_id else None
    if _current_user_id.get() != uid:   # new request/user → fresh session totals
        _current_user_id.set(uid)
        reset_session_usage()


def get_usage_user() -> Optional[str]:
    return _current_user_id.get()


def set_usage_entity(entity_type=None, entity_id=None, entity_label=None) -> None:
    """Tag subsequent agent calls with an entity (e.g. a job) so they're queryable +
    badged. log_call uses this as a fallback when the agent doesn't pass its own."""
    _current_entity.set({
        "type": entity_type,
        "id": str(entity_id) if entity_id else None,
        "label": entity_label,
    })


def get_session_usage() -> dict:
    return _session_usage.get() or {"tokens": 0, "cost_inr": 0.0}


def get_last_usage():
    return _last_usage.get()

# Approximate USD pricing per 1M tokens.
PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25},
    "claude-opus-4-5": {"input": 15.0, "output": 75.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
}
USD_TO_INR = 83.5


def estimate_anthropic_cost(input_tokens: int, output_tokens: int, model: str):
    pricing = PRICING.get(model, {"input": 3.0, "output": 15.0})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost_usd, 6), round(cost_usd * USD_TO_INR, 4)


async def log_anthropic_usage(
    session: AsyncSession,
    user_id: uuid.UUID,
    agent_name: str,
    category: str,
    input_tokens: int,
    output_tokens: int,
    model: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    entity_label: Optional[str] = None,
    result_summary: Optional[str] = None,
) -> None:
    """Log an Anthropic API call to the usage log (adds + flushes on the given session)."""
    total = (input_tokens or 0) + (output_tokens or 0)
    cost_usd, cost_inr = estimate_anthropic_cost(input_tokens or 0, output_tokens or 0, model)
    session.add(APIUsageLog(
        user_id=user_id,
        provider="anthropic",
        agent_name=agent_name,
        category=category,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        entity_label=entity_label,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        estimated_cost_usd=cost_usd,
        estimated_cost_inr=cost_inr,
        result_summary=result_summary,
    ))
    await session.flush()


async def log_apify_usage(
    session: AsyncSession,
    user_id: uuid.UUID,
    actor_id: str,
    feed_label: str,
    runs_requested: int,
    runs_returned: int,
    jobs_saved: int,
    cost_usd: float,
    entity_id: Optional[str] = None,
) -> None:
    """Log an Apify actor run to the usage log."""
    session.add(APIUsageLog(
        user_id=user_id,
        provider="apify",
        agent_name=actor_id,
        category="scanner",
        entity_type="scan",
        entity_id=str(entity_id) if entity_id else None,
        entity_label=feed_label,
        actor_id=actor_id,
        runs_requested=runs_requested,
        runs_returned=runs_returned,
        jobs_saved=jobs_saved,
        estimated_cost_usd=round(cost_usd or 0.0, 6),
        estimated_cost_inr=round((cost_usd or 0.0) * USD_TO_INR, 4),
    ))
    await session.flush()


async def log_call(agent_name: str, category: str, response, model: str,
                   entity_type: Optional[str] = None, entity_id=None,
                   entity_label: Optional[str] = None,
                   result_summary: Optional[str] = None) -> None:
    """Agent-facing helper: read token counts off an Anthropic response's `.usage`,
    attribute to the contextvar user, and log fire-and-forget. Never raises, no-ops
    when there's no current user. Call right after `client.messages.create(...)`."""
    user_id = get_usage_user()
    try:
        usage = getattr(response, "usage", None)
        in_t = int(getattr(usage, "input_tokens", 0) or 0)
        out_t = int(getattr(usage, "output_tokens", 0) or 0)
    except Exception:
        in_t, out_t = 0, 0

    total = in_t + out_t
    _usd, inr = estimate_anthropic_cost(in_t, out_t, model)
    # Accumulate per-request totals + remember the last call (read by endpoints for badges).
    sess = get_session_usage()
    _session_usage.set({"tokens": sess["tokens"] + total, "cost_inr": round(sess["cost_inr"] + inr, 4)})
    _last_usage.set({"tokens": total, "cost_inr": round(inr, 4)})

    if not user_id:
        return
    ent = _current_entity.get() or {}
    await log_anthropic_usage_safe(
        user_id, agent_name, category, in_t, out_t, model,
        entity_type=entity_type or ent.get("type"),
        entity_id=entity_id or ent.get("id"),
        entity_label=entity_label or ent.get("label"),
        result_summary=result_summary)


async def log_anthropic_usage_safe(user_id, agent_name, category, input_tokens,
                                   output_tokens, model, **kwargs) -> None:
    """Fire-and-forget variant that manages its own session — for agents (Celery tasks,
    deep call stacks) that don't have a session handy. Never raises."""
    if not user_id:
        return
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await log_anthropic_usage(session, user_id, agent_name, category,
                                      input_tokens, output_tokens, model, **kwargs)
            await session.commit()
    except Exception as e:  # logging must never break the main op
        print(f"⚠️ usage log failed ({agent_name}): {e}")

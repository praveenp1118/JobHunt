"""
Helper to resolve the effective Claude model for a user.
Priority: user's preferred_model > settings.ANTHROPIC_MODEL > fallback
"""
from typing import Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings

FALLBACK_MODEL = "claude-sonnet-4-5"

VALID_MODELS = {
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
}


async def get_user_model(
    user_id: uuid.UUID,
    session: AsyncSession,
) -> str:
    """
    Get the effective model string for a user.
    Returns their preferred_model if set and valid, otherwise settings default.

    Also marks this user as the current usage-attribution subject — every
    agent call in this request task logs against them (see usage_logger).
    """
    from app.models.user import UserPreferences
    from app.utils.usage_logger import set_usage_user
    set_usage_user(user_id)

    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()

    if prefs and prefs.preferred_model and prefs.preferred_model in VALID_MODELS:
        return prefs.preferred_model

    model = getattr(settings, 'anthropic_model', None) or FALLBACK_MODEL
    return model if model in VALID_MODELS else FALLBACK_MODEL

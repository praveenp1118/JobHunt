"""
Razorpay billing — PARALLEL to the Stripe module (routers/billing.py) during the
provider migration. TEST MODE ONLY until live keys are intentionally set. Stripe stays
fully functional; nothing here touches Stripe.

Writes the SAME provider-agnostic entitlement columns is_entitled() reads
(subscription_status / subscription_end / subscription_plan) + entitlement_source and
the Razorpay ids — so a Razorpay-activated user becomes is_entitled=True with ZERO
change to is_entitled or the invite path.

Razorpay's Python SDK is synchronous → SDK calls run in asyncio.to_thread.

LIVE-HARDENING BACKLOG (do NOT ship live without these — see CLAUDE.md backlog):
  - Webhook idempotency: subscription.charged can be delivered more than once, and
    both the webhook and /verify call _activate() setting subscription_end = now+30d,
    so duplicate delivery could OVER-EXTEND the subscription. Before live cutover, key
    activation on the payment_id (dedupe) or set subscription_end from the billing
    cycle end (current_end) instead of now+30d.
  - The /verify poll compounds the same over-extension. Fix alongside the above.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.auth.dependencies import current_active_user

logger = logging.getLogger("razorpay_billing")
router = APIRouter()

PRO_PERIOD = timedelta(days=30)
SUBSCRIPTION_TOTAL_COUNT = 120  # Razorpay has no infinite sub; 120 monthly cycles = 10yr


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client() -> razorpay.Client:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay is not configured (missing keys).")
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def _activate(user: User) -> None:
    """Write the SHARED entitlement columns is_entitled() reads + the Razorpay source.
    Explicitly sets entitlement_source (the Stripe handler has a pre-existing bug where
    it never does).

    LIVE-HARDENING: setting subscription_end = now+30d on every call is not idempotent —
    see the module docstring backlog before live cutover."""
    user.subscription_status = "active"
    user.subscription_plan = "pro"
    user.subscription_end = _now() + PRO_PERIOD
    user.entitlement_source = "razorpay"
    user.payment_provider = "razorpay"


# ── Create subscription ───────────────────────────────────────────────────────
class SubscribeRequest(BaseModel):
    plan: str = "pro"


@router.post("/razorpay/create-subscription")
async def create_subscription(
    body: SubscribeRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if not settings.razorpay_plan_id:
        raise HTTPException(status_code=503, detail="Razorpay not configured (missing razorpay_plan_id).")
    if body.plan != "pro":
        raise HTTPException(status_code=400, detail="Unknown plan")
    client = _client()
    try:
        sub = await asyncio.to_thread(client.subscription.create, {
            "plan_id": settings.razorpay_plan_id,
            "total_count": SUBSCRIPTION_TOTAL_COUNT,
            "customer_notify": 1,
            "notes": {"user_id": str(user.id)},
        })
    except Exception as e:  # razorpay.errors.*
        logger.error("Razorpay subscription create failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Razorpay error: {str(e)}")

    user.razorpay_subscription_id = sub.get("id")
    if sub.get("customer_id"):
        user.razorpay_customer_id = sub.get("customer_id")
    await session.commit()
    # SAME response shape as the Stripe checkout ({checkout_url}) so the frontend barely changes.
    return {"checkout_url": sub.get("short_url"), "subscription_id": sub.get("id")}


# ── Cancel (at cycle end) ─────────────────────────────────────────────────────
@router.post("/razorpay/cancel")
async def cancel_subscription(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if not user.razorpay_subscription_id:
        raise HTTPException(status_code=400, detail="No Razorpay subscription to cancel")
    client = _client()
    try:
        await asyncio.to_thread(client.subscription.cancel,
                                user.razorpay_subscription_id, {"cancel_at_cycle_end": 1})
    except Exception as e:
        logger.error("Razorpay cancel failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Razorpay error: {str(e)}")
    user.subscription_status = "cancelled"
    await session.commit()
    return {"message": "Subscription will cancel at the end of the current cycle"}


# ── Verify (success-page poll; webhook is the source of truth) ────────────────
@router.get("/razorpay/verify")
async def verify_subscription(
    subscription_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if subscription_id != user.razorpay_subscription_id:
        raise HTTPException(status_code=403, detail="Not your subscription")
    client = _client()
    try:
        sub = await asyncio.to_thread(client.subscription.fetch, subscription_id)
    except Exception as e:
        logger.error("Razorpay verify fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Razorpay error: {str(e)}")
    status = sub.get("status")
    if status in ("active", "authenticated", "charged"):
        _activate(user)
        await session.commit()
        return {"success": True, "plan": "pro", "status": status}
    return {"success": False, "status": status}


# ── Webhook (Razorpay HMAC-SHA256 signature, no auth) ─────────────────────────
async def _user_by_sub(session: AsyncSession, sub_id: str):
    if not sub_id:
        return None
    return (await session.execute(
        select(User).where(User.razorpay_subscription_id == sub_id))).scalar_one_or_none()


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_db)):
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook secret not configured")
    # HMAC-SHA256(raw_body, webhook_secret) — same scheme razorpay.Utility.verify_webhook_signature
    # uses. REJECT on mismatch: never process an unsigned/forged event.
    expected = hmac.new(settings.razorpay_webhook_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not (signature and hmac.compare_digest(expected, signature)):
        logger.warning("Razorpay webhook signature mismatch")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(raw)
    etype = event.get("event", "")
    sub_entity = (((event.get("payload") or {}).get("subscription") or {}).get("entity") or {})
    sub_id = sub_entity.get("id")
    notes = sub_entity.get("notes") or {}

    try:
        user = await _user_by_sub(session, sub_id)
        if not user and notes.get("user_id"):
            try:
                user = (await session.execute(
                    select(User).where(User.id == uuid.UUID(notes["user_id"])))).scalar_one_or_none()
            except (ValueError, TypeError):
                user = None
        if not user:
            logger.warning("Razorpay webhook %s: no matching user (sub %s)", etype, sub_id)
            return {"status": "ok"}

        if etype in ("subscription.activated", "subscription.charged"):
            if not user.razorpay_subscription_id and sub_id:
                user.razorpay_subscription_id = sub_id
            _activate(user)
            await session.commit()
        elif etype == "subscription.pending":
            user.subscription_status = "past_due"
            await session.commit()
        elif etype == "subscription.halted":
            user.subscription_status = "expired"
            await session.commit()
        elif etype in ("subscription.cancelled", "subscription.completed"):
            user.subscription_status = "expired"
            user.subscription_plan = "none"
            await session.commit()
    except Exception:  # never 500 a webhook — Razorpay retries on non-2xx
        logger.exception("Razorpay webhook handler error for %s", etype)

    return {"status": "ok"}

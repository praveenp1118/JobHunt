"""
Billing router — JobHunt Pro subscription via Stripe.

Stripe SDK calls are synchronous, so they're run in a threadpool (asyncio.to_thread)
to avoid blocking the event loop. The webhook is the source of truth for subscription
state; verify-session is a best-effort fallback so the success page can confirm
immediately without waiting for the webhook to land.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.auth.dependencies import current_active_user

logger = logging.getLogger("billing")
router = APIRouter()

# Configure the SDK once (api_key may be empty until keys are set in .env).
stripe.api_key = settings.stripe_secret_key

PRO_PERIOD = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_configured():
    if not settings.stripe_secret_key or not settings.stripe_pro_price_id:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured (missing stripe_secret_key / stripe_pro_price_id).",
        )


def _g(obj, key, default=None):
    """Safe field access for Stripe objects. This SDK's StripeObject does NOT expose
    dict.get() — `.get` routes through __getattr__ and raises — but bracket access works."""
    try:
        val = obj[key]
    except (KeyError, TypeError, AttributeError):
        return default
    return default if val is None else val


class CheckoutRequest(BaseModel):
    plan: str = "pro"
    success_url: str
    cancel_url: str


# ── Create checkout session ───────────────────────────────────────────────────
@router.post("/create-checkout-session")
async def create_checkout_session(
    body: CheckoutRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    _ensure_configured()
    if body.plan != "pro":
        raise HTTPException(status_code=400, detail="Unknown plan")

    # 1. Get or create the Stripe customer for this user.
    if not user.stripe_customer_id:
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            email=user.email,
            name=user.name or None,
            metadata={"user_id": str(user.id)},
        )
        user.stripe_customer_id = customer.id
        await session.commit()

    # 2. Create the subscription checkout session.
    try:
        checkout = await asyncio.to_thread(
            stripe.checkout.Session.create,
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": settings.stripe_pro_price_id, "quantity": 1}],
            mode="subscription",
            success_url=body.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=body.cancel_url,
            metadata={"user_id": str(user.id)},
        )
    except stripe.StripeError as e:  # type: ignore[attr-defined]
        logger.error("Stripe checkout create failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    return {"checkout_url": checkout.url}


# ── Current subscription ──────────────────────────────────────────────────────
@router.get("/subscription")
async def get_subscription(user: User = Depends(current_active_user)):
    from app.utils.subscription import is_entitled
    return {
        "plan": user.subscription_plan,
        "status": user.subscription_status,
        "subscription_end": user.subscription_end,
        # How access was obtained — 'invite' | 'stripe' | None. Drives the UI
        # (invite users see "Request extension"; stripe users see "Manage plan").
        "entitlement_source": user.entitlement_source,
        # stripe_customer_id is intentionally NOT exposed to the frontend.
        "has_customer": bool(user.stripe_customer_id),
        # Expiry-aware: an invite whose free period lapsed reads is_active=False
        # even though status is still 'active' (no webhook flips invite status).
        "is_active": is_entitled(user),
    }


# ── Which provider the frontend should use ────────────────────────────────────
@router.get("/provider")
async def get_payment_provider():
    """Which billing provider the frontend should use ('stripe' | 'razorpay'). Public —
    not sensitive; lets us flip providers via config without a frontend redeploy."""
    p = settings.payment_provider if settings.payment_provider in ("stripe", "razorpay") else "stripe"
    return {"provider": p}


# ── Cancel (at period end) ────────────────────────────────────────────────────
@router.post("/cancel")
async def cancel_subscription(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    _ensure_configured()
    if not user.subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")
    try:
        await asyncio.to_thread(
            stripe.Subscription.modify, user.subscription_id, cancel_at_period_end=True
        )
    except stripe.StripeError as e:  # type: ignore[attr-defined]
        logger.error("Stripe cancel failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    user.subscription_status = "cancelled"
    await session.commit()
    return {"message": "Subscription will cancel at period end"}


# ── Webhook (Stripe signature, no auth) ───────────────────────────────────────
async def _user_by_id(session: AsyncSession, user_id: str):
    try:
        import uuid
        return (await session.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    except (ValueError, TypeError):
        return None


async def _user_by_customer(session: AsyncSession, customer_id: str):
    if not customer_id:
        return None
    return (await session.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )).scalar_one_or_none()


@router.post("/webhook")
async def stripe_webhook(request: Request, session: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except (ValueError, stripe.SignatureVerificationError) as e:  # type: ignore[attr-defined]
        logger.warning("Stripe webhook signature/parse failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    obj = event["data"]["object"]

    try:
        if etype == "checkout.session.completed":
            user = await _user_by_id(session, _g(_g(obj, "metadata") or {}, "user_id", ""))
            if not user:
                user = await _user_by_customer(session, _g(obj, "customer"))
            if user:
                user.subscription_status = "active"
                user.subscription_plan = "pro"
                user.subscription_id = _g(obj, "subscription")
                user.stripe_customer_id = _g(obj, "customer") or user.stripe_customer_id
                user.subscription_end = _now() + PRO_PERIOD
                await session.commit()

        elif etype == "invoice.payment_succeeded":
            user = await _user_by_customer(session, _g(obj, "customer"))
            if user:
                user.subscription_status = "active"
                user.subscription_plan = "pro"
                user.subscription_end = _now() + PRO_PERIOD
                await session.commit()

        elif etype == "invoice.payment_failed":
            user = await _user_by_customer(session, _g(obj, "customer"))
            if user:
                user.subscription_status = "past_due"
                await session.commit()

        elif etype == "customer.subscription.deleted":
            user = await _user_by_customer(session, _g(obj, "customer"))
            if user:
                user.subscription_status = "expired"
                user.subscription_plan = "none"
                await session.commit()
    except Exception:  # never 500 a webhook — Stripe will retry storms
        logger.exception("Webhook handler error for %s", etype)

    return {"status": "ok"}


# ── Verify session (success-page polling) ─────────────────────────────────────
@router.get("/verify-session")
async def verify_session(
    session_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    _ensure_configured()
    try:
        checkout = await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
    except stripe.StripeError as e:  # type: ignore[attr-defined]
        logger.error("verify-session retrieve failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    # Only activate from a session that belongs to this user.
    owns = (
        _g(_g(checkout, "metadata") or {}, "user_id") == str(user.id)
        or _g(checkout, "customer") == user.stripe_customer_id
    )
    if _g(checkout, "payment_status") == "paid" and owns:
        user.subscription_status = "active"
        user.subscription_plan = "pro"
        if _g(checkout, "subscription"):
            user.subscription_id = _g(checkout, "subscription")
        user.stripe_customer_id = _g(checkout, "customer") or user.stripe_customer_id
        user.subscription_end = _now() + PRO_PERIOD
        await session.commit()
        return {"success": True, "plan": "pro"}
    return {"success": False}

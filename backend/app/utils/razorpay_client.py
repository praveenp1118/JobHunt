"""Shared Razorpay client + cleanup helpers.

One home for the razorpay.Client setup, the "is this a Razorpay user?" test, and the
subscription-cancel cleanup — reused by the billing router (subscribe/cancel/verify/
webhook) AND the ancillary provider-aware call sites (account purge, data-deletion) so
none of it is duplicated. Runtime-only (the SDK is called for a real user); importing
this module needs no live key, so it is safe to build/test while the account is under review.
"""
import razorpay

from app.config import settings


def is_razorpay_user(user) -> bool:
    """True when the user's active provider is Razorpay — either the explicit flag or a
    stored subscription id. Mirrors the create/verify seam that sets
    payment_provider='razorpay'."""
    return getattr(user, "payment_provider", None) == "razorpay" or bool(
        getattr(user, "razorpay_subscription_id", None))


def get_razorpay_client() -> razorpay.Client:
    """A configured Razorpay client, or raise RuntimeError if the keys are unset. Callers
    in an HTTP context translate this to a 503 (see the billing router); background callers
    (purge / deletion) catch it and continue so a missing key can't block cleanup."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay is not configured (missing keys).")
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def cancel_razorpay_subscription(subscription_id: str, at_cycle_end: bool) -> None:
    """Cancel a Razorpay subscription (synchronous SDK call — wrap in asyncio.to_thread
    from async contexts).

    at_cycle_end=True  → let the paid period run out, but STOP future charges. Use for a
                         user-initiated cancel or a deletion request (the e-mandate must stop).
    at_cycle_end=False → cancel immediately. Use for an account purge — there is no reason
                         to keep the mandate alive once the account is gone. (Razorpay has
                         no "delete customer" like Stripe, so cancelling the subscription
                         IS the cleanup.)"""
    if not subscription_id:
        return
    client = get_razorpay_client()
    client.subscription.cancel(subscription_id, {"cancel_at_cycle_end": 1 if at_cycle_end else 0})

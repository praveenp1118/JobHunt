"""Razorpay billing (parallel provider, TEST mode) — webhook entitlement + signature.

Calls the webhook handler IN-PROCESS (not via the live server) so monkeypatch on
settings.razorpay_webhook_secret takes effect — the in-container uvicorn server runs
in a separate process where a pytest monkeypatch wouldn't reach."""
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings

WEBHOOK_SECRET = "whsec_test_razorpay_fake"   # not a real credential


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


class _FakeRequest:
    """Minimal stand-in for starlette Request — the webhook only uses .body()/.headers."""
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    async def body(self) -> bytes:
        return self._body


async def test_razorpay_webhook_activates_entitlement(monkeypatch):
    """A signed subscription.charged flips the SHARED entitlement columns → is_entitled=True,
    with zero change to is_entitled."""
    from app.routers.razorpay_billing import razorpay_webhook
    from app.models.user import User
    from app.utils.subscription import is_entitled
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)

    eng, S = _sm()
    uid = uuid.uuid4()
    try:
        async with S() as s:
            s.add(User(id=uid, email=f"rzp-{uid}@t.co", hashed_password="x", is_active=True,
                       is_superuser=False, is_verified=True, name="Rzp",
                       subscription_status="inactive"))
            await s.commit()

        payload = {"event": "subscription.charged",
                   "payload": {"subscription": {"entity": {
                       "id": "sub_test123", "notes": {"user_id": str(uid)}}}}}
        body = json.dumps(payload).encode()
        req = _FakeRequest(body, {"X-Razorpay-Signature": _sign(body)})
        async with S() as s:
            res = await razorpay_webhook(req, s)
        assert res == {"status": "ok"}

        async with S() as s:
            u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            assert u.subscription_status == "active" and u.subscription_plan == "pro"
            assert u.entitlement_source == "razorpay" and u.payment_provider == "razorpay"
            assert u.subscription_end is not None
            assert is_entitled(u) is True
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()


async def test_razorpay_webhook_rejects_bad_signature(monkeypatch):
    from app.routers.razorpay_billing import razorpay_webhook
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)

    body = json.dumps({"event": "subscription.charged", "payload": {}}).encode()
    req = _FakeRequest(body, {"X-Razorpay-Signature": "deadbeef"})
    eng, S = _sm()
    try:
        async with S() as s:
            with pytest.raises(HTTPException) as ei:
                await razorpay_webhook(req, s)
        assert ei.value.status_code == 400
    finally:
        await eng.dispose()


# ── Stage 3: ancillary provider-aware cancels (deletion request) ──────────────
async def _run_delete_request(monkeypatch, *, provider_fields):
    """Create a user with the given provider fields, call the privacy delete-request
    handler in-process (audit_log stubbed), and record which provider's cancel was hit."""
    from app.routers.privacy import request_deletion, DeleteRequest
    from app.models.user import User
    import app.utils.razorpay_client as rzp_util
    import app.utils.audit_logger as audit_mod
    import stripe

    calls = {"rzp": [], "stripe": []}
    monkeypatch.setattr(rzp_util, "cancel_razorpay_subscription",
                        lambda sub_id, at_cycle_end: calls["rzp"].append((sub_id, at_cycle_end)))
    monkeypatch.setattr(stripe.Subscription, "modify",
                        lambda *a, **k: calls["stripe"].append((a, k)), raising=False)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(audit_mod, "audit_log", _noop)

    eng, S = _sm()
    uid = uuid.uuid4()
    try:
        async with S() as s:
            s.add(User(id=uid, email=f"del-{uid}@t.co", hashed_password="x", is_active=True,
                       is_superuser=False, is_verified=True, name="Del",
                       subscription_status="active", **provider_fields))
            await s.commit()
        async with S() as s:
            u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            res = await request_deletion(DeleteRequest(confirm=True), None, u, s)
        assert res["scheduled"] is True
        async with S() as s:
            u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            return calls, u
    finally:
        async with S() as s:
            await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
            await s.commit()
        await eng.dispose()


async def test_deletion_razorpay_user_cancels_razorpay(monkeypatch):
    """A Razorpay user's deletion request cancels the Razorpay subscription at cycle end
    (stops the e-mandate) and NEVER touches Stripe."""
    calls, u = await _run_delete_request(monkeypatch, provider_fields={
        "payment_provider": "razorpay", "razorpay_subscription_id": "sub_del123"})
    assert calls["rzp"] == [("sub_del123", True)]   # at_cycle_end=True
    assert calls["stripe"] == []
    assert u.subscription_status == "cancelled"
    assert u.data_deletion_scheduled_at is not None


async def test_deletion_stripe_user_cancels_stripe(monkeypatch):
    """A Stripe user's deletion request still cancels via Stripe (byte-identical path) and
    NEVER touches Razorpay."""
    calls, u = await _run_delete_request(monkeypatch, provider_fields={
        "payment_provider": None, "subscription_id": "sub_stripe123"})
    assert calls["rzp"] == []
    assert len(calls["stripe"]) == 1
    args, kwargs = calls["stripe"][0]
    assert args[0] == "sub_stripe123" and kwargs.get("cancel_at_period_end") is True
    assert u.subscription_status == "cancelled"

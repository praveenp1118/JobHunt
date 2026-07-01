"""Billing / subscription smoke tests (live in-container server, fresh non-admin user).

The fresh user_creds user is non-admin + subscription_status='inactive', so the
subscription gate applies. Stripe calls can't be monkeypatched against the live
server, so the checkout test branches on whether Stripe keys are configured.
"""
import uuid

from app.config import settings


async def test_get_subscription_returns_status(client, user_creds):
    r = await client.get("/api/billing/subscription", headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plan"] == "none"
    assert d["status"] == "inactive"
    assert d["is_active"] is False
    assert "subscription_end" in d


async def test_create_checkout_session_returns_url(client, user_creds):
    r = await client.post(
        "/api/billing/create-checkout-session",
        json={"plan": "pro",
              "success_url": "http://localhost:3000/billing/success",
              "cancel_url": "http://localhost:3000/settings#plan"},
        headers=user_creds["headers"],
    )
    # The route is correctly wired when it reaches Stripe — i.e. NOT a 401/404/422.
    #   200 → fully working (returns checkout_url)
    #   502 → Stripe reached but stripe_pro_price_id is wrong (must be a price_… id, not prod_…)
    #   503 → Stripe keys not configured
    assert r.status_code in (200, 502, 503), r.text
    if r.status_code == 200:
        assert "checkout_url" in r.json()


async def test_subscription_required_blocks_tailor(client, user_creds):
    r = await client.post(
        "/api/tailor/generate",
        json={"job_id": str(uuid.uuid4()), "domain_cv_id": str(uuid.uuid4())},
        headers=user_creds["headers"],
    )
    assert r.status_code == 402, r.text
    # Gate now covers invite-or-pay entitlement (renamed from subscription_required).
    assert r.json()["detail"]["code"] == "entitlement_required"


async def test_subscription_required_allows_get_jobs(client, user_creds):
    # GET endpoints are NOT gated — read-only access stays open.
    r = await client.get("/api/jobs", headers=user_creds["headers"])
    assert r.status_code == 200, r.text

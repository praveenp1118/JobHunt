"""
Invite-or-pay registration gate — smoke tests.

Covers: key redemption (valid / used / revoked / expired / invalid), a two-user
race on one key (exactly one winner), the subscription gate on a Claude endpoint
(non-entitled → 402, invited-lapsed → 402, admin → bypass), and extension-request
persistence (saves even when the admin email can't be sent).

Runs against the live in-container server (real HTTP + Postgres), like the rest of
the suite. Admin/user rows are created + torn down per test.
"""
import asyncio
import uuid

import asyncpg
import pytest

from app.config import settings

PASSWORD = "TestPass123!"


def _dsn() -> str:
    return settings.database_url.replace("+asyncpg", "")


async def _register(client, name="Invite Test"):
    email = f"pytest_{uuid.uuid4().hex[:12]}@example.com"
    r = await client.post("/api/auth/register",
                          json={"email": email, "password": PASSWORD, "name": name})
    assert r.status_code in (200, 201), r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"email": email, "headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}


async def _promote_admin(client, email):
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("UPDATE users SET role='admin' WHERE email=$1", email)
    finally:
        await conn.close()
    # Re-login so the token carries the new role.
    r = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _backdate_entitlement(email, source="invite"):
    """Simulate a lapsed free period: active status but subscription_end in the past."""
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(
            "UPDATE users SET subscription_status='active', entitlement_source=$1, "
            "subscription_end = now() - interval '1 day' WHERE email=$2", source, email)
    finally:
        await conn.close()


async def _delete(email):
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("DELETE FROM users WHERE email=$1", email)
    finally:
        await conn.close()


async def _make_admin(client):
    a = await _register(client, "Admin")
    a["headers"] = await _promote_admin(client, a["email"])
    return a


async def _create_key(client, admin, grants_days=30, key_expires_at=None):
    body = {"count": 1, "grants_days": grants_days}
    if key_expires_at is not None:
        body["key_expires_at"] = key_expires_at
    r = await client.post("/api/admin/invites", json=body, headers=admin["headers"])
    assert r.status_code == 200, r.text
    return r.json()["keys"][0]["code"]


# ── 1. Valid key → active + source=invite ─────────────────────────────────────
async def test_redeem_valid_key_activates_user(client):
    admin = await _make_admin(client)
    u = await _register(client)
    try:
        code = await _create_key(client, admin, grants_days=30)
        r = await client.post("/api/invites/redeem", json={"code": code}, headers=u["headers"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["redeemed"] is True and body["entitlement_source"] == "invite"

        me = (await client.get("/api/auth/me", headers=u["headers"])).json()
        assert me["subscription_status"] == "active"
        assert me["entitlement_source"] == "invite"

        # Now entitled → passes the gate (reaches 404 for a missing job, not 402).
        g = await client.post(f"/api/jobs/{uuid.uuid4()}/score-now", headers=u["headers"])
        assert g.status_code == 404
    finally:
        await _delete(u["email"]); await _delete(admin["email"])


# ── 2. Used key → 4xx ─────────────────────────────────────────────────────────
async def test_redeem_used_key_rejected(client):
    admin = await _make_admin(client)
    u1 = await _register(client); u2 = await _register(client)
    try:
        code = await _create_key(client, admin)
        r1 = await client.post("/api/invites/redeem", json={"code": code}, headers=u1["headers"])
        assert r1.status_code == 200, r1.text
        r2 = await client.post("/api/invites/redeem", json={"code": code}, headers=u2["headers"])
        assert r2.status_code == 400
        assert r2.json()["detail"]["code"] == "key_used"
    finally:
        await _delete(u1["email"]); await _delete(u2["email"]); await _delete(admin["email"])


# ── 3. Revoked key → 4xx ──────────────────────────────────────────────────────
async def test_redeem_revoked_key_rejected(client):
    admin = await _make_admin(client)
    u = await _register(client)
    try:
        # Create then revoke via the admin endpoints.
        r = await client.post("/api/admin/invites", json={"count": 1}, headers=admin["headers"])
        key = r.json()["keys"][0]
        rev = await client.post(f"/api/admin/invites/{key['id']}/revoke", headers=admin["headers"])
        assert rev.status_code == 200, rev.text
        red = await client.post("/api/invites/redeem", json={"code": key["code"]}, headers=u["headers"])
        assert red.status_code == 400
        assert red.json()["detail"]["code"] == "key_revoked"
    finally:
        await _delete(u["email"]); await _delete(admin["email"])


# ── 4. Expired key → 4xx ──────────────────────────────────────────────────────
async def test_redeem_expired_key_rejected(client):
    admin = await _make_admin(client)
    u = await _register(client)
    try:
        code = await _create_key(client, admin, key_expires_at="2020-01-01T00:00:00+00:00")
        r = await client.post("/api/invites/redeem", json={"code": code}, headers=u["headers"])
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "key_expired"
    finally:
        await _delete(u["email"]); await _delete(admin["email"])


# ── 5. Invalid/unknown key → 404 ──────────────────────────────────────────────
async def test_redeem_unknown_key_404(client):
    u = await _register(client)
    try:
        r = await client.post("/api/invites/redeem", json={"code": "JH-ZZZZ-ZZZZ"}, headers=u["headers"])
        assert r.status_code == 404
    finally:
        await _delete(u["email"])


# ── 6. Race: two users, one key → exactly one wins ────────────────────────────
async def test_two_users_racing_one_key_single_winner(client):
    admin = await _make_admin(client)
    u1 = await _register(client); u2 = await _register(client)
    try:
        code = await _create_key(client, admin)
        r1, r2 = await asyncio.gather(
            client.post("/api/invites/redeem", json={"code": code}, headers=u1["headers"]),
            client.post("/api/invites/redeem", json={"code": code}, headers=u2["headers"]),
        )
        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [200, 400], f"expected one winner, got {statuses}: {r1.text} | {r2.text}"
    finally:
        await _delete(u1["email"]); await _delete(u2["email"]); await _delete(admin["email"])


# ── 7. Non-entitled user hits a gated Claude endpoint → 402 ───────────────────
async def test_non_entitled_score_now_402(client, user_creds):
    r = await client.post(f"/api/jobs/{uuid.uuid4()}/score-now", headers=user_creds["headers"])
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "entitlement_required"


# ── 8. Invited-but-lapsed user → 402 (expiry-aware gate) ──────────────────────
async def test_invited_lapsed_user_402(client):
    u = await _register(client)
    try:
        await _backdate_entitlement(u["email"], source="invite")
        # status is 'active' but subscription_end is in the past → lapsed → blocked.
        r = await client.post(f"/api/jobs/{uuid.uuid4()}/score-now", headers=u["headers"])
        assert r.status_code == 402, r.text
        assert r.json()["detail"]["code"] == "entitlement_required"
    finally:
        await _delete(u["email"])


# ── 9. Admin bypasses the gate even with no subscription ──────────────────────
async def test_admin_bypasses_gate(client):
    admin = await _make_admin(client)
    try:
        # Admin has subscription_status='inactive' but the gate exempts admins:
        # they reach the endpoint (404 for a missing job), NOT 402.
        r = await client.post(f"/api/jobs/{uuid.uuid4()}/score-now", headers=admin["headers"])
        assert r.status_code == 404, r.text
    finally:
        await _delete(admin["email"])


# ── 10. Extension request saves even when the admin email can't be sent ───────
async def test_extension_request_saves_even_without_smtp(client):
    u = await _register(client)
    try:
        # The container has no deliverable SMTP creds, so the notification send is a
        # no-op/failure — but the request row must still be created (source of truth).
        r = await client.post("/api/extension-requests", headers=u["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["pending"] is True
        mine = await client.get("/api/extension-requests", headers=u["headers"])
        assert mine.status_code == 200
        rows = mine.json()
        assert len(rows) >= 1 and rows[0]["status"] == "pending"
    finally:
        await _delete(u["email"])

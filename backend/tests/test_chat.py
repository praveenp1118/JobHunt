"""Support chat tests — rule-based FAQ + REST endpoints (live in-container server).

FAQ matching is pure; the API tests create guest conversations (cleaned up by
guest_email) and use the owner (admin) token for admin-only paths (skipped if the
owner isn't present).
"""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.utils.chat_faq import match_faq, get_no_match_response

OWNER_ID = uuid.UUID("fff12f28-0ee6-41df-85ad-490b1391c716")


# ── Pure FAQ rule tests ───────────────────────────────────────────────────────
def test_faq_match_anthropic_key():
    r = match_faq("where do I get my anthropic api key?")
    assert r is not None and r["id"] == "anthropic_key"


def test_faq_match_gmail_password():
    r = match_faq("my gmail app password is not working")
    assert r is not None and r["id"] == "gmail_password"


def test_faq_no_match_creates_suggestion():
    assert match_faq("xyzzy totally unrelated gibberish") is None
    assert "ticket" in get_no_match_response().lower()


# ── helpers ───────────────────────────────────────────────────────────────────
async def _owner_headers():
    from app.auth.config import get_jwt_strategy
    from app.models.user import User
    eng = create_async_engine(settings.database_url)
    Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            u = (await s.execute(select(User).where(User.id == OWNER_ID))).scalar_one_or_none()
            if not u:
                return None
            return {"Authorization": f"Bearer {await get_jwt_strategy().write_token(u)}"}
    finally:
        await eng.dispose()


async def _delete_conv(email):
    eng = create_async_engine(settings.database_url)
    Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            await s.execute(text("delete from chat_conversations where guest_email = :e"), {"e": email})
            await s.commit()
    finally:
        await eng.dispose()


# ── API tests ─────────────────────────────────────────────────────────────────
async def test_create_conversation_guest(client):
    email = f"guest_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/chat/conversations", json={
        "guest_name": "Test Guest", "guest_email": email,
        "first_message": "what is the pricing for the subscription?"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["conversation_id"]
    assert isinstance(d["admin_online"], bool)
    if not d["admin_online"]:
        assert d["bot_response"] and d["bot_response"]["content"]  # pricing FAQ matched
    await _delete_conv(email)


async def test_create_conversation_user(client, user_creds):
    r = await client.post("/api/chat/conversations",
                          json={"first_message": "hello support team"},
                          headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["conversation_id"]
    # Tied to the user → removed by the user_creds teardown (users CASCADE).


async def test_faq_no_match_creates_suggestion_api(client):
    email = f"guest_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/chat/conversations", json={
        "guest_name": "G", "guest_email": email, "first_message": "qwerty zxcv nomatch"})
    d = r.json()
    if not d["admin_online"]:
        assert d["bot_response"] and d["bot_response"].get("no_match") is True
    await _delete_conv(email)


async def test_send_message_admin(client):
    h = await _owner_headers()
    if not h:
        pytest.skip("owner not present")
    email = f"guest_{uuid.uuid4().hex[:8]}@example.com"
    cid = (await client.post("/api/chat/conversations", json={
        "guest_name": "G", "guest_email": email, "first_message": "hi"})).json()["conversation_id"]
    m = await client.post(f"/api/chat/conversations/{cid}/messages",
                          json={"content": "Hi, how can I help?"}, headers=h)
    assert m.status_code == 200, m.text
    assert m.json()["message"]["sender_type"] == "admin"
    await _delete_conv(email)


async def test_create_ticket(client):
    email = f"guest_{uuid.uuid4().hex[:8]}@example.com"
    cid = (await client.post("/api/chat/conversations", json={
        "guest_name": "G", "guest_email": email,
        "first_message": "I need help with billing"})).json()["conversation_id"]
    t = await client.post("/api/chat/tickets", json={"conversation_id": cid, "priority": "high"})
    assert t.status_code == 200, t.text
    assert t.json()["ticket_number"].startswith("JH-")
    await _delete_conv(email)


async def test_admin_presence_online(client):
    h = await _owner_headers()
    if not h:
        pytest.skip("owner not present")
    try:
        r = await client.post("/api/chat/presence", json={"is_online": True}, headers=h)
        assert r.status_code == 200
        g = await client.get("/api/chat/presence")
        assert g.json()["is_online"] is True
    finally:
        await client.post("/api/chat/presence", json={"is_online": False}, headers=h)


async def test_admin_presence_offline_timeout(client):
    h = await _owner_headers()
    if not h:
        pytest.skip("owner not present")
    await client.post("/api/chat/presence", json={"is_online": True}, headers=h)
    # Backdate last_seen beyond the 5-minute window → GET should report offline.
    eng = create_async_engine(settings.database_url)
    Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            await s.execute(text(
                "update admin_presence set last_seen = now() - interval '6 minutes' where admin_id = :a"),
                {"a": str(OWNER_ID)})
            await s.commit()
    finally:
        await eng.dispose()
    g = await client.get("/api/chat/presence")
    assert g.json()["is_online"] is False
    await client.post("/api/chat/presence", json={"is_online": False}, headers=h)

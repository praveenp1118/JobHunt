"""
Pytest fixtures for API smoke tests.

These tests run against the LIVE uvicorn server inside the backend container
(real HTTP, real Postgres) rather than in-process, which sidesteps the
pytest-asyncio cross-event-loop reuse problem with the module-level async engine.

Override the target with API_BASE_URL if needed (defaults to the in-container server).
"""
import os
import uuid

import asyncpg
import pytest_asyncio
from httpx import AsyncClient

from app.config import settings

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _sync_dsn() -> str:
    """Plain libpq DSN for asyncpg (strip SQLAlchemy's +asyncpg driver suffix)."""
    return settings.database_url.replace("+asyncpg", "")


async def _delete_user(email: str) -> None:
    """Delete a user row directly. DB-level ON DELETE CASCADE removes the
    associated user_preferences / user_credentials / wallets / wallet_transactions.
    Uses a fresh asyncpg connection (not the app's shared engine) so teardown is
    isolated from the per-test event loop."""
    conn = await asyncpg.connect(_sync_dsn())
    try:
        await conn.execute("DELETE FROM users WHERE email = $1", email)
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest_asyncio.fixture
async def user_creds(client):
    """Register a fresh, non-admin user, yield its credentials + auth headers,
    then delete the user on teardown so each run leaves the DB clean."""
    email = f"pytest_{uuid.uuid4().hex[:12]}@example.com"
    password = "TestPass123!"

    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "name": "Pytest User"},
    )
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"

    r = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]

    try:
        yield {
            "email": email,
            "password": password,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    finally:
        # Best-effort cleanup — never fail a passing test because teardown hiccupped.
        try:
            await _delete_user(email)
        except Exception as e:  # pragma: no cover - diagnostic only
            print(f"⚠️ test user cleanup failed for {email}: {e}")

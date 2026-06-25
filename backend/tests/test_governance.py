"""Governance + security tests — rate limiting, hallucination, prompt injection,
data export/deletion, login lockout, isolation, masking, audit logging."""
import inspect
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.utils.cv_validator import validate_no_hallucination
from app.utils.rate_limiter import enforce_rate_limit

OWNER = uuid.UUID("fff12f28-0ee6-41df-85ad-490b1391c716")


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _mk_user(session):
    from app.models.user import User
    uid = uuid.uuid4()
    session.add(User(id=uid, email=f"gov_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False))
    await session.flush()
    return uid


async def _cleanup_user(session, uid):
    await session.execute(text("delete from users where id = :u"), {"u": str(uid)})
    await session.commit()


# ── Hallucination (pure) ──
def test_hallucination_catches_invented_number():
    master = "Drove 40% cost reduction and scaled to $4.5M revenue over 15 years."
    r = validate_no_hallucination("Delivered 88% growth and $99M revenue.", master)
    assert r["valid"] is False
    vals = [v["value"] for v in r["violations"]]
    assert "88%" in vals


def test_hallucination_passes_valid_cv():
    master = "Drove 40% cost reduction and scaled to $4.5M revenue over 15 years."
    r = validate_no_hallucination("Reframed the 40% reduction; $4.5M revenue over 15 years.", master)
    assert r["valid"] is True


# ── Prompt injection hardening (source inspection) ──
def test_prompt_injection_xml_tags_present():
    from app.agents import jd_agents, tailor_agents, career_agent
    jd_src = inspect.getsource(jd_agents.parse_and_score_jd)
    assert "<job_description>" in jd_src and "SECURITY INSTRUCTION" in jd_src
    tl_src = inspect.getsource(tailor_agents.generate_tailor_package)
    assert "<cv_content>" in tl_src and "SECURITY INSTRUCTION" in tl_src
    assert "SECURITY INSTRUCTION" in career_agent.SYSTEM_PROMPT


# ── Rate limiting (DB) ──
async def test_rate_limit_blocks_after_limit():
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            # career_analyse limit = 3 → 3 allowed, 4th raises 429
            for _ in range(3):
                await enforce_rate_limit(uid, "career_analyse", s)
            with pytest.raises(HTTPException) as ei:
                await enforce_rate_limit(uid, "career_analyse", s)
            assert ei.value.status_code == 429
            await _cleanup_user(s, uid)
    finally:
        await eng.dispose()


async def test_rate_limit_resets_after_window():
    from app.models.governance import RateLimitLog
    from datetime import datetime, timezone, timedelta
    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            # Insert 3 usages OUTSIDE the 24h window → should not count
            old = datetime.now(timezone.utc) - timedelta(hours=48)
            for _ in range(3):
                s.add(RateLimitLog(user_id=uid, action="career_analyse", count=1, window_start=old))
            await s.flush()
            res = await enforce_rate_limit(uid, "career_analyse", s)  # must be allowed
            assert res["allowed"] is True
            await _cleanup_user(s, uid)
    finally:
        await eng.dispose()


# ── Data export + deletion (API) ──
async def test_data_export_returns_zip(client):
    from app.auth.config import get_jwt_strategy
    from app.models.user import User
    eng, S = _sm()
    try:
        async with S() as s:
            u = (await s.execute(select(User).where(User.id == OWNER))).scalar_one_or_none()
            if not u:
                pytest.skip("owner absent")
            tok = await get_jwt_strategy().write_token(u)
        r = await client.get("/api/privacy/export", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert r.content[:2] == b"PK"  # ZIP magic
    finally:
        await eng.dispose()


async def test_deletion_request_schedules_30_days(client, user_creds):
    r = await client.post("/api/privacy/delete-request", json={"confirm": True}, headers=user_creds["headers"])
    assert r.status_code == 200 and r.json()["scheduled"] is True
    assert r.json()["grace_days"] == 30
    # cleanup
    await client.post("/api/privacy/cancel-deletion", headers=user_creds["headers"])


async def test_deletion_cancel_clears_schedule(client, user_creds):
    await client.post("/api/privacy/delete-request", json={"confirm": True}, headers=user_creds["headers"])
    c = await client.post("/api/privacy/cancel-deletion", headers=user_creds["headers"])
    assert c.status_code == 200 and c.json()["cancelled"] is True
    s = await client.get("/api/privacy/summary", headers=user_creds["headers"])
    assert s.json()["data_deletion_scheduled"] is None


# ── Login lockout (Redis) ──
async def test_login_lockout_after_5_failures(client):
    from app.utils.login_security import clear_attempts
    email = f"lockout_{uuid.uuid4().hex[:10]}@example.com"
    try:
        for _ in range(5):
            await client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        r = await client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 429
    finally:
        await clear_attempts(email)


# ── Data isolation ──
async def test_user_isolation_jobs_only_own_data(client, user_creds):
    from app.auth.config import get_jwt_strategy
    from app.models.user import User
    from app.models.job import Job
    eng, S = _sm()
    try:
        async with S() as s:
            u = (await s.execute(select(User).where(User.id == OWNER))).scalar_one_or_none()
            if not u:
                pytest.skip("owner absent")
            job = (await s.execute(select(Job).where(Job.user_id == OWNER).limit(1))).scalar_one_or_none()
            if not job:
                pytest.skip("owner has no jobs")
            jid = job.id
        # A different user (user_creds) must NOT be able to read the owner's job.
        r = await client.get(f"/api/jobs/{jid}", headers=user_creds["headers"])
        assert r.status_code == 404
    finally:
        await eng.dispose()


# ── Sensitive data masking ──
async def test_credentials_never_return_key_values(client, user_creds):
    await client.put("/api/auth/me/credentials", json={"anthropic_api_key": "FAKEKEY_not_a_real_secret_123"},
                     headers=user_creds["headers"])
    r = await client.get("/api/auth/me/credentials", headers=user_creds["headers"])
    body = r.text
    assert "FAKEKEY_not_a_real_secret_123" not in body
    assert r.json()["has_anthropic_key"] is True
    assert "anthropic_api_key_enc" not in body and "anthropic_api_key" not in r.json()


# ── Audit logging ──
async def test_audit_log_records_login(client):
    email = f"audit_{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/api/auth/register", json={"email": email, "password": "TestPass123!", "name": "Audit"})
    await client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
    eng, S = _sm()
    try:
        async with S() as s:
            from app.models.governance import AuditLog
            from app.models.user import User
            uid = (await s.execute(select(User.id).where(User.email == email))).scalar_one()
            rows = (await s.execute(select(AuditLog).where(
                AuditLog.user_id == uid, AuditLog.action == "login_success"))).scalars().all()
            assert len(rows) >= 1
            await s.execute(text("delete from users where email = :e"), {"e": email})
            await s.commit()
    finally:
        await eng.dispose()

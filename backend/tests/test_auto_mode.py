"""Auto-mode integration test — the full tailor pipeline WITHOUT browser interaction:
auto_mode ON → generate → bulk-approve → apply → verify the package.

Uses the owner's real master CV + an active domain CV + a job and makes REAL Claude
calls (generate + apply, ~30-60s). Skips gracefully if those prerequisites aren't
present (e.g. a clean CI database). Restores the owner's original auto_mode at the end.
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.config import settings

OWNER_ID = uuid.UUID("fff12f28-0ee6-41df-85ad-490b1391c716")


async def test_auto_mode_full_tailor_pipeline(client):
    from app.models.user import User
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.job import Job
    from app.auth.config import get_jwt_strategy

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            user = (await s.execute(select(User).where(User.id == OWNER_ID))).scalar_one_or_none()
            if not user:
                pytest.skip("owner user not present (clean DB) — live auto-mode test skipped")
            master = (await s.execute(select(MasterCV).where(
                MasterCV.user_id == OWNER_ID, MasterCV.is_active == True))).scalars().first()
            dcv = (await s.execute(select(DomainCV).where(
                DomainCV.user_id == OWNER_ID, DomainCV.status == CVStatus.active,
                DomainCV.content_md.isnot(None)))).scalars().first()
            job = (await s.execute(select(Job).where(Job.user_id == OWNER_ID).limit(1))).scalar_one_or_none()
            if not (master and dcv and job):
                pytest.skip("owner master CV / active domain CV / job not present — skipped")
            token = await get_jwt_strategy().write_token(user)
    finally:
        await engine.dispose()

    H = {"Authorization": f"Bearer {token}"}

    # Remember the original auto_mode so we can restore it afterwards.
    original = (await client.get("/api/auth/me/preferences", headers=H)).json().get("auto_mode")
    try:
        # 1. auto_mode ON (PATCH returns a message; confirm via GET)
        r = await client.patch("/api/auth/me/preferences", json={"auto_mode": True}, headers=H)
        assert r.status_code == 200
        assert (await client.get("/api/auth/me/preferences", headers=H)).json().get("auto_mode") is True

        # 2. generate (simulates the auto-mode page load)
        g = await client.post("/api/tailor/generate",
                              json={"job_id": str(job.id), "domain_cv_id": str(dcv.id)},
                              headers=H, timeout=150)
        assert g.status_code == 200, g.text
        tid = g.json()["tailored_cv_id"]

        # 3. changelog generated
        cl = (await client.get(f"/api/tailor/{tid}/changelog", headers=H)).json()
        assert isinstance(cl, list)

        # 4. bulk approve all
        b = await client.post(f"/api/tailor/{tid}/changelog/bulk",
                              json={"action": "approve_all"}, headers=H)
        assert b.status_code == 200

        # 5. apply
        a = await client.post(f"/api/tailor/{tid}/apply", headers=H, timeout=150)
        assert a.status_code == 200, a.text
        d = a.json()

        # 6. verify the full package
        assert d.get("tailored_cv_md"), "tailored_cv_md is empty"
        assert d.get("cover_letter_md"), "cover_letter_md is empty"
        email = d.get("email_draft") or ""
        assert email, "email_draft is empty"
        assert any(tok in email for tok in ("Hi ", "Dear ", "Hello", "regards")), \
            f"email_draft has no greeting/sign-off: {email[:120]!r}"
        assert (d.get("s2_score") or 0) > 0, "s2_score not positive"
        assert (d.get("s3_master") or 0) > 0, "s3_master not positive"
        assert d.get("s3_status") in ("green", "amber"), f"unexpected s3_status: {d.get('s3_status')}"
    finally:
        # Restore the owner's original auto_mode setting.
        if original is not None:
            await client.patch("/api/auth/me/preferences", json={"auto_mode": original}, headers=H)

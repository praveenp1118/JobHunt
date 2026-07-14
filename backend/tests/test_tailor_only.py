"""Standalone cover-letter-only / email-only paths (skip Suggest-changes + CV tailoring).

Verifies: creates a TailoredCV when none exists (cv_md='', no change log), updates just the
one field, and REUSES an existing record (no duplicate). Agents mocked — no real Claude."""
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _seed(S, uid, jid, mcv_id, dcv_id):
    """user + active master + a domain CV + a partial-less job. Skips if industry/function
    seed rows are absent (DomainCV FKs)."""
    from app.models.user import User
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.job import Job, JobSource, JobStatus
    async with S() as s:
        ind = (await s.execute(text("SELECT id FROM industry_verticals LIMIT 1"))).scalar()
        fn = (await s.execute(text("SELECT id FROM functional_disciplines LIMIT 1"))).scalar()
        if not ind or not fn:
            return False
    async with S() as s:
        s.add(User(id=uid, email=f"t-{uid}@t.co", hashed_password="x", is_active=True,
                   is_superuser=False, is_verified=True, name="T"))
        await s.commit()
    async with S() as s:
        s.add(MasterCV(id=mcv_id, user_id=uid, is_active=True, content_md="MASTER CV BODY",
                       essence_json={"keywords": ["product"]}))
        await s.commit()
    async with S() as s:
        s.add(DomainCV(id=dcv_id, user_id=uid, master_cv_id=mcv_id, industry_id=ind,
                       function_id=fn, country_code="NL", status=CVStatus.active,
                       content_md="DOMAIN CV BODY"))
        s.add(Job(id=jid, user_id=uid, company="Acme", role="Head of Product",
                  jd_raw="Full JD text for the role. " * 10, jd_md="Full JD text. " * 10,
                  dedup_key=f"url:t/{jid}", source=JobSource.rss, status=JobStatus.new))
        await s.commit()
    return True


async def _cleanup(S, uid):
    async with S() as s:
        # Break the circular FK first (jobs.tailored_cv_id → tailored_cvs, NO ACTION).
        await s.execute(text("UPDATE jobs SET tailored_cv_id=NULL WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM change_logs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM tailored_cvs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM domain_cvs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM master_cvs WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM rate_limit_log WHERE user_id=:u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
        await s.commit()


async def test_cover_letter_only_creates_minimal_record(monkeypatch):
    from fastapi import Response
    import app.routers.tailor as tr
    from app.routers.tailor import cover_letter_only
    from app.models.user import User
    from app.models.cv import TailoredCV, ChangeLog
    from app.models.job import Job

    async def fake_cl(**k):
        return ("COVER LETTER TEXT", "story_led")
    monkeypatch.setattr(tr, "regenerate_cover_letter", fake_cl)

    eng, S = _sm()
    uid, jid, mcv, dcv = (uuid.uuid4() for _ in range(4))
    try:
        if not await _seed(S, uid, jid, mcv, dcv):
            await eng.dispose(); pytest.skip("industry/function seed rows absent")
        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            res = await cover_letter_only(jid, Response(), user, s)
        assert res["cover_letter_md"] == "COVER LETTER TEXT"
        async with S() as s:
            tcv = (await s.execute(select(TailoredCV).where(TailoredCV.job_id == jid))).scalar_one()
            assert tcv.cover_letter_md == "COVER LETTER TEXT"
            assert tcv.cv_md == "" and tcv.email_draft is None and tcv.status == "generated"
            n_changes = (await s.execute(select(func.count()).select_from(ChangeLog)
                         .where(ChangeLog.tailored_cv_id == tcv.id))).scalar()
            assert n_changes == 0                                   # NO change log
            job = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert job.tailored_cv_id == tcv.id                     # linked
    finally:
        await _cleanup(S, uid); await eng.dispose()


async def test_email_only_creates_minimal_record(monkeypatch):
    from fastapi import Response
    import app.routers.tailor as tr
    from app.routers.tailor import email_only
    from app.models.user import User
    from app.models.cv import TailoredCV, ChangeLog

    async def fake_email(**k):
        return "EMAIL BODY"
    monkeypatch.setattr(tr, "generate_email_draft", fake_email)

    eng, S = _sm()
    uid, jid, mcv, dcv = (uuid.uuid4() for _ in range(4))
    try:
        if not await _seed(S, uid, jid, mcv, dcv):
            await eng.dispose(); pytest.skip("industry/function seed rows absent")
        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            res = await email_only(jid, Response(), user, s)
        assert res["email_draft"] == "EMAIL BODY"
        async with S() as s:
            tcv = (await s.execute(select(TailoredCV).where(TailoredCV.job_id == jid))).scalar_one()
            assert tcv.email_draft == "EMAIL BODY" and tcv.cv_md == "" and tcv.cover_letter_md is None
            n_changes = (await s.execute(select(func.count()).select_from(ChangeLog)
                         .where(ChangeLog.tailored_cv_id == tcv.id))).scalar()
            assert n_changes == 0
    finally:
        await _cleanup(S, uid); await eng.dispose()


async def test_only_reuses_existing_record_no_duplicate(monkeypatch):
    """A job that already has a TailoredCV (from Generate-All) → the only-paths UPDATE that
    row (no duplicate) and never touch cv_md / the existing change log."""
    from fastapi import Response
    import app.routers.tailor as tr
    from app.routers.tailor import cover_letter_only, email_only
    from app.models.user import User
    from app.models.cv import TailoredCV, ChangeLog, ChangeType, ChangeStatus
    from app.models.job import Job

    async def fake_cl(**k):
        return ("NEW CL", "concise")
    async def fake_email(**k):
        return "NEW EMAIL"
    monkeypatch.setattr(tr, "regenerate_cover_letter", fake_cl)
    monkeypatch.setattr(tr, "generate_email_draft", fake_email)

    eng, S = _sm()
    uid, jid, mcv, dcv, tcv_id = (uuid.uuid4() for _ in range(5))
    try:
        if not await _seed(S, uid, jid, mcv, dcv):
            await eng.dispose(); pytest.skip("industry/function seed rows absent")
        # Pre-existing full tailoring: a TailoredCV with cv_md + one change-log row.
        async with S() as s:
            s.add(TailoredCV(id=tcv_id, user_id=uid, job_id=jid, domain_cv_id=dcv,
                             cv_md="ORIGINAL TAILORED CV", cover_letter_md="OLD CL",
                             email_draft="OLD EMAIL", status="applied", s2=80.0))
            await s.flush()
            s.add(ChangeLog(user_id=uid, tailored_cv_id=tcv_id, change_type=ChangeType.rephrase,
                            section="EXPERIENCE", original_text="a", proposed_text="b",
                            status=ChangeStatus.approved))
            job = (await s.execute(select(Job).where(Job.id == jid))).scalar_one()
            job.tailored_cv_id = tcv_id
            await s.commit()

        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            await cover_letter_only(jid, Response(), user, s)
        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            await email_only(jid, Response(), user, s)

        async with S() as s:
            rows = (await s.execute(select(TailoredCV).where(TailoredCV.job_id == jid))).scalars().all()
            assert len(rows) == 1                                   # NO duplicate
            t = rows[0]
            assert t.id == tcv_id
            assert t.cover_letter_md == "NEW CL" and t.email_draft == "NEW EMAIL"   # updated
            assert t.cv_md == "ORIGINAL TAILORED CV"                # cv_md untouched
            n_changes = (await s.execute(select(func.count()).select_from(ChangeLog)
                         .where(ChangeLog.tailored_cv_id == tcv_id))).scalar()
            assert n_changes == 1                                   # change log untouched
    finally:
        await _cleanup(S, uid); await eng.dispose()

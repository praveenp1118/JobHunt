"""A failed/successful one-time essence call must never break the CV save.
Reproduces the MissingGreenlet-on-serialize bug in POST /cvs/master/upload|text."""
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings

CV_MD = "# Jane Doe\n\n## Experience\n" + ("- Led product teams and shipped AI features. " * 12)


def _sm():
    # Match the app session config (expire_on_commit=False) to reproduce faithfully.
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _mk_user(session):
    from app.models.user import User
    from datetime import datetime, timezone, timedelta
    uid = uuid.uuid4()
    # Essence is now gated on entitlement (only entitled users spend tokens), so this
    # user must be entitled for the success path to actually run the essence call.
    session.add(User(id=uid, email=f"cv_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False,
                     subscription_status="active", entitlement_source="stripe",
                     subscription_end=datetime.now(timezone.utc) + timedelta(days=30)))
    await session.flush()
    return uid


async def _run(monkeypatch, essence_fn):
    from app.routers.cvs import _save_master_cv
    from app.models.cv import MasterCV
    from app.models.user import User

    async def _fake_key(user, session):
        return "fake-key"
    monkeypatch.setattr("app.routers.cvs._get_anthropic_key", _fake_key)
    monkeypatch.setattr("app.agents.essence_agent.extract_cv_essence", essence_fn)

    eng, S = _sm()
    try:
        async with S() as s:
            uid = await _mk_user(s)
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            out = await _save_master_cv(user, s, CV_MD, "test upload")  # must NOT raise
            m = (await s.execute(select(MasterCV).where(MasterCV.user_id == uid))).scalars().first()
            res = (out.version, m.essence_json)
            await s.execute(text("delete from users where id = :u"), {"u": str(uid)})
            await s.commit()
            return res
    finally:
        await eng.dispose()


# Essence SUCCEEDS (commits) — the real bug: serialization must not MissingGreenlet.
async def test_master_save_succeeds_when_essence_succeeds(monkeypatch):
    async def _ok(cv_md, version, **kw):
        return {"keywords": ["product", "ai"], "core_identity": "Senior PM"}
    version, essence = await _run(monkeypatch, _ok)
    assert version == 1
    assert essence is not None and "keywords" in essence


# Essence RAISES — isolation: the CV is still saved, essence stays None, no 500.
async def test_master_save_succeeds_when_essence_raises(monkeypatch):
    async def _boom(cv_md, version, **kw):
        raise RuntimeError("Claude exploded mid-essence")
    version, essence = await _run(monkeypatch, _boom)
    assert version == 1
    assert essence is None


# ── Regression: domain-CV regenerate arg-order (Bug A) ──────────────────────
async def test_regenerate_domain_cv_passes_real_user_not_session(monkeypatch):
    """POST /cvs/domains/{id}/regenerate called generate_domain_cv_changelog with
    swapped positional args → the AsyncSession landed in `user` → user.id AttributeError
    (500). The `user` arg must be a real User, `session` a real session — not swapped."""
    from fastapi import Response
    import app.routers.cvs as cvs
    from app.models.user import User
    from app.models.cv import MasterCV, DomainCV, CVStatus
    from app.models.domain import IndustryVertical, FunctionalDiscipline

    captured = {}
    async def fake_generate(body, response, user, session):
        captured["user"] = user
        captured["session"] = session
    async def fake_bulk(domain_cv_id, body, user, session):
        return None
    async def fake_apply(domain_cv_id, user, session):
        return {"regenerated": True}
    monkeypatch.setattr(cvs, "generate_domain_cv_changelog", fake_generate)
    monkeypatch.setattr(cvs, "bulk_change_action", fake_bulk)
    monkeypatch.setattr(cvs, "apply_domain_cv_changes", fake_apply)

    eng, S = _sm()
    dcv_id = uuid.uuid4()
    uid = None
    try:
        async with S() as s:
            ind = (await s.execute(select(IndustryVertical.id).limit(1))).scalar()
            fn = (await s.execute(select(FunctionalDiscipline.id).limit(1))).scalar()
            if not ind or not fn:
                return  # seed data absent (fresh DB) — skip cleanly
            uid = await _mk_user(s)
            mcv = MasterCV(id=uuid.uuid4(), user_id=uid, content_md="M", word_count=10,
                           is_active=True, version=1)
            s.add(mcv); await s.flush()
            s.add(DomainCV(id=dcv_id, user_id=uid, master_cv_id=mcv.id, industry_id=ind,
                           function_id=fn, country_code="NL", content_md="D",
                           status=CVStatus.stale, version=1))
            await s.commit()

        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            result = await cvs.regenerate_domain_cv(
                domain_cv_id=dcv_id, response=Response(), user=user, session=s)

        assert result == {"regenerated": True}            # no 500
        assert isinstance(captured["user"], User)          # user arg is a real User…
        assert captured["user"].id == uid                  # …the right one
        assert not isinstance(captured["session"], User)   # …session wasn't swapped in
    finally:
        if uid is not None:
            async with S() as s:
                await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
                await s.commit()
        await eng.dispose()


# ── Regenerate updates in place, keeps job references (FK fix) ──────────────
async def test_regenerate_domain_cv_updates_in_place_keeping_job_refs(monkeypatch):
    """Regenerating a domain CV that a job references must UPDATE in place (same id,
    version bumped) — no FK violation, and jobs' best_domain_cv_id/domain_cv_scores
    stay valid. Against the old delete+insert this raised IntegrityError."""
    import app.routers.cvs as cvs
    from fastapi import Response
    from app.schemas.cv import DomainCVCreate
    from app.models.user import User
    from app.models.cv import MasterCV, DomainCV, DomainCVVersion, CVStatus
    from app.models.job import Job, JobSource, JobStatus
    from app.models.domain import IndustryVertical, FunctionalDiscipline, CountryMaster

    # No Claude: empty changelog + fake key + fake model.
    async def _no_changes(**kw):
        return []
    async def _fake_key(user, session):
        return "fake-key"
    async def _fake_model(uid, session):
        return "claude-haiku-4-5"
    monkeypatch.setattr(cvs, "generate_domain_changelog", _no_changes)
    monkeypatch.setattr(cvs, "_get_anthropic_key", _fake_key)
    monkeypatch.setattr(cvs, "get_user_model", _fake_model)

    eng, S = _sm()
    dcv_id, job_id = uuid.uuid4(), uuid.uuid4()
    uid = None
    try:
        async with S() as s:
            ind = (await s.execute(select(IndustryVertical.id).limit(1))).scalar()
            fn = (await s.execute(select(FunctionalDiscipline.id).limit(1))).scalar()
            cc = (await s.execute(select(CountryMaster.country_code).limit(1))).scalar()
            if not ind or not fn or not cc:
                return  # seed data absent — skip cleanly
            uid = await _mk_user(s)
            mcv = MasterCV(id=uuid.uuid4(), user_id=uid, content_md="MASTER v2", word_count=10,
                           is_active=True, version=2)
            s.add(mcv); await s.flush()
            s.add(DomainCV(id=dcv_id, user_id=uid, master_cv_id=mcv.id, industry_id=ind,
                           function_id=fn, country_code=cc, content_md="OLD CONTENT",
                           status=CVStatus.active, version=1, s3_domain=90.0, s3_master=80.0))
            # A job referencing this domain CV (as today's backfill set).
            s.add(Job(id=job_id, user_id=uid, company="Acme", role="Head of Product", market="NL",
                      source=JobSource.rss, status=JobStatus.new, jd_raw="x",
                      best_domain_cv_id=dcv_id, domain_cv_scores={str(dcv_id): 88}))
            await s.commit()

        async with S() as s:
            user = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            body = DomainCVCreate(industry_id=ind, function_id=fn, country_code=cc)
            res = await cvs.generate_domain_cv_changelog(
                body=body, response=Response(), user=user, session=s)   # must NOT raise

        assert res["domain_cv_id"] == str(dcv_id)   # same id (no delete+insert)
        assert res["version"] == 2                   # bumped
        async with S() as s:
            dcv = (await s.execute(select(DomainCV).where(DomainCV.id == dcv_id))).scalar_one()
            assert dcv.version == 2 and dcv.status == CVStatus.regenerating
            assert dcv.master_cv_id == mcv.id
            # Referencing job still points at the SAME (refreshed) CV — nothing wiped.
            job = (await s.execute(select(Job).where(Job.id == job_id))).scalar_one()
            assert job.best_domain_cv_id == dcv_id
            assert job.domain_cv_scores == {str(dcv_id): 88}
            # Old content archived to version history.
            vers = (await s.execute(select(DomainCVVersion).where(
                DomainCVVersion.domain_cv_id == dcv_id))).scalars().all()
            assert any(v.content_md == "OLD CONTENT" and v.version == 1 for v in vers)
    finally:
        if uid is not None:
            async with S() as s:
                await s.execute(text("DELETE FROM jobs WHERE user_id=:u"), {"u": str(uid)})
                await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": str(uid)})
                await s.commit()
        await eng.dispose()

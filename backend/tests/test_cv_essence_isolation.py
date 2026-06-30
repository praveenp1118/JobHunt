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
    uid = uuid.uuid4()
    session.add(User(id=uid, email=f"cv_{uid.hex[:10]}@example.com",
                     hashed_password="x", is_active=True, is_superuser=False, is_verified=False))
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

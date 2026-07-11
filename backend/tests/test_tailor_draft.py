"""Tailor draft persistence — a saved draft is restored on return (ZERO Claude),
and a non-forced generate returns the existing draft instead of re-running."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings


def _sm():
    eng = create_async_engine(settings.database_url)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _uid(client, headers):
    return uuid.UUID((await client.get("/api/auth/me", headers=headers)).json()["id"])


async def _seed(s, uid, *, applied=True, base_ver=3, tailor_jd_hash="jdh1",
                dcv_version=3, job_jd_hash="jdh1"):
    """Seed industry/function/master/domain/job/tailored/changelogs for one user.
    Returns the created ids. ind/fn are NOT user-scoped → caller cleans them up."""
    from app.models.domain import IndustryVertical, FunctionalDiscipline
    from app.models.cv import (MasterCV, DomainCV, TailoredCV, ChangeLog,
                               ChangeType, ChangeStatus, CVStatus)
    from app.models.job import Job, JobSource, JobStatus

    ind = IndustryVertical(id=uuid.uuid4(), code=f"T{uuid.uuid4().hex[:5]}", label="Test Ind")
    fn = FunctionalDiscipline(id=uuid.uuid4(), code=f"T{uuid.uuid4().hex[:5]}", label="Test Fn")
    s.add_all([ind, fn]); await s.flush()
    master = MasterCV(id=uuid.uuid4(), user_id=uid, content_md="# Master", version=1, is_active=True)
    s.add(master); await s.flush()
    dcv = DomainCV(id=uuid.uuid4(), user_id=uid, master_cv_id=master.id, industry_id=ind.id,
                   function_id=fn.id, country_code="NL", content_md="# Domain CV",
                   version=dcv_version, status=CVStatus.active)
    s.add(dcv); await s.flush()
    job = Job(id=uuid.uuid4(), user_id=uid, company="Acme", role="Head of Product", market="NL",
              source=JobSource.manual, status=JobStatus.new, jd_raw="JD text", jd_md="JD text",
              jd_hash=job_jd_hash)
    s.add(job); await s.flush()
    tailored = TailoredCV(
        id=uuid.uuid4(), user_id=uid, job_id=job.id, domain_cv_id=dcv.id,
        cv_md=("TAILORED CV CONTENT" if applied else ""),
        cover_letter_md="COVER LETTER", email_draft="EMAIL BODY",
        s2=72.0, s3_domain=(95.0 if applied else None), s3_master=(92.0 if applied else None),
        cl_template_used="story_led", status=("applied" if applied else "generated"),
        applied_at=(datetime.now(timezone.utc) if applied else None),
        base_domain_cv_version=base_ver, jd_hash=tailor_jd_hash)
    s.add(tailored); await s.flush()
    s.add_all([
        ChangeLog(id=uuid.uuid4(), user_id=uid, tailored_cv_id=tailored.id,
                  change_type=ChangeType.rephrase, section="SUMMARY", original_text="old",
                  proposed_text="new", final_text="new", status=ChangeStatus.approved),
        ChangeLog(id=uuid.uuid4(), user_id=uid, tailored_cv_id=tailored.id,
                  change_type=ChangeType.keyword_injection, section="EXPERIENCE",
                  original_text="a", proposed_text="b", status=ChangeStatus.rejected),
    ])
    job.tailored_cv_id = tailored.id
    await s.commit()
    return {"job_id": job.id, "dcv_id": dcv.id, "tailored_id": tailored.id,
            "ind_id": ind.id, "fn_id": fn.id}


async def _cleanup(s, uid, ids):
    # Delete the user first (CASCADE removes master/domain/job/tailored/changelog), THEN the
    # (non-user-scoped) industry/function rows, now unreferenced. The fixture's own teardown
    # then no-ops on the already-deleted user.
    await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
    await s.execute(text("DELETE FROM industry_verticals WHERE id = :i"), {"i": str(ids["ind_id"])})
    await s.execute(text("DELETE FROM functional_disciplines WHERE id = :f"), {"f": str(ids["fn_id"])})
    await s.commit()


# ── applied draft → full restore, zero Claude ──
async def test_draft_restores_full_applied_package(client, user_creds):
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds["headers"])
        async with S() as s:
            ids = await _seed(s, uid, applied=True)
        r = await client.get(f"/api/tailor/job/{ids['job_id']}/draft", headers=user_creds["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["exists"] is True
        assert d["status"] == "applied"
        assert d["tailored_cv_id"] == str(ids["tailored_id"])
        assert d["domain_cv_id"] == str(ids["dcv_id"])
        assert d["cv_md"] == "TAILORED CV CONTENT"
        assert d["cover_letter_md"] == "COVER LETTER" and d["email_draft"] == "EMAIL BODY"
        assert d["s2"] == 72.0 and d["s3_domain"] == 95.0 and d["s3_master"] == 92.0
        assert d["s3_status"] == "green"   # 92 >= review threshold (90)
        assert len(d["changelog"]) == 2
        assert {c["status"] for c in d["changelog"]} == {"approved", "rejected"}
        assert d["stale"] == {"base_cv_changed": False, "jd_changed": False}
        async with S() as s:
            await _cleanup(s, uid, ids)
    finally:
        await eng.dispose()


# ── no draft → exists:false ──
async def test_draft_absent_returns_exists_false(client, user_creds):
    from app.models.job import Job, JobSource, JobStatus
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds["headers"])
        jid = uuid.uuid4()
        async with S() as s:
            s.add(Job(id=jid, user_id=uid, company="ZZ", role="PM", market="NL",
                      source=JobSource.manual, status=JobStatus.new, jd_raw="x"))
            await s.commit()
        r = await client.get(f"/api/tailor/job/{jid}/draft", headers=user_creds["headers"])
        assert r.status_code == 200 and r.json()["exists"] is False
    finally:
        await eng.dispose()


# ── non-forced generate returns the existing draft — no Claude, no key needed ──
async def test_generate_force_false_returns_existing(client, active_user_creds):
    eng, S = _sm()
    ids = None
    try:
        uid = await _uid(client, active_user_creds["headers"])
        async with S() as s:
            ids = await _seed(s, uid, applied=True)
        # Entitled user with NO Anthropic key: if this called Claude it would fail; instead the
        # return-existing branch short-circuits and hands back the SAME tailored_cv_id.
        r = await client.post("/api/tailor/generate",
                              json={"job_id": str(ids["job_id"]), "domain_cv_id": str(ids["dcv_id"]),
                                    "force": False},
                              headers=active_user_creds["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["tailored_cv_id"] == str(ids["tailored_id"])
    finally:
        if ids:
            async with S() as s:
                await _cleanup(s, uid, ids)
        await eng.dispose()


# ── staleness flags when base CV version or JD hash drifted ──
async def test_staleness_flags(client, user_creds):
    eng, S = _sm()
    try:
        uid = await _uid(client, user_creds["headers"])
        async with S() as s:
            ids = await _seed(s, uid, applied=True, base_ver=2, dcv_version=3,
                              tailor_jd_hash="old", job_jd_hash="new")
        r = await client.get(f"/api/tailor/job/{ids['job_id']}/draft", headers=user_creds["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["stale"] == {"base_cv_changed": True, "jd_changed": True}
        async with S() as s:
            await _cleanup(s, uid, ids)
    finally:
        await eng.dispose()

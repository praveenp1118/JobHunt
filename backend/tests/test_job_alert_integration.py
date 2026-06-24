"""V3 Gmail job-alert parser — mocked integration test for the orchestrator
`process_job_alert_email`.

External deps are stubbed so this is deterministic and CI-safe:
  - fetch_url_content  -> fake JD text (no network)
  - parse_and_score_jd -> fake parse + S1 score (no Claude)
  - title pre-filter    -> disabled via prefs (no Playwright)

It runs against the real Postgres using a FRESH engine (created + disposed
inside the test) to stay isolated from the per-test event loop, and cleans up
the rows it creates.
"""
import uuid
from unittest.mock import patch

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.models.user import User, UserRole, UserPlan
from app.models.job import Job, EmailThread, JobSource, EmailClassification, EmailDirection
import app.agents.gmail_alert_agent as agent_mod
import app.agents.jd_agents as jd_mod


class _Prefs:
    parse_job_alerts = True
    job_alert_max_links = 10
    job_alert_title_filter = False   # skip Playwright in this test
    s1_min_threshold = 65
    target_roles = "Head of Product,VP Product"
    preferred_model = None


ALERT_HTML = """<html><body>
  <a href="https://careers.x.com/jobs/1-vp-product">VP Product</a>
  <a href="https://careers.x.com/jobs/2-barista">Barista</a>
  <a href="https://x.com/unsubscribe">unsubscribe</a>
</body></html>"""


async def _fake_fetch(url):
    return f"Job description at {url} " + "x" * 200


async def _fake_parse(raw_text, master_cv_md, user_anthropic_key=None, model=None):
    # VP Product scores high (saved), barista scores low (dropped)
    if "vp-product" in raw_text:
        return {"parsed": {"company": "Acme", "role": "VP Product", "location": "Amsterdam",
                           "market": "NL", "jd_language": "en"}, "s1_score": 90}
    return {"parsed": {"company": "Acme", "role": "Barista"}, "s1_score": 20}


async def test_process_job_alert_email_saves_only_qualifying_jobs():
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    user_id = uuid.uuid4()
    et_id = uuid.uuid4()
    try:
        async with Session() as session:
            user = User(
                id=user_id, email=f"alerttest_{user_id.hex[:8]}@example.com",
                hashed_password="x", is_active=True, is_superuser=False, is_verified=False,
                role=UserRole.user, plan=UserPlan.default,
            )
            session.add(user)
            await session.flush()  # insert the user before anything FKs to it

            email_thread = EmailThread(
                id=et_id, user_id=user_id, job_id=None,
                direction=EmailDirection.received,
                classification=EmailClassification.job_alert, is_job_alert=True,
            )
            session.add(email_thread)
            await session.flush()

            with patch.object(jd_mod, "fetch_url_content", _fake_fetch), \
                 patch.object(jd_mod, "parse_and_score_jd", _fake_parse):
                res = await agent_mod.process_job_alert_email(
                    email_thread, ALERT_HTML, user, session,
                    anthropic_key="k", model=None, prefs=_Prefs(),
                )
            await session.commit()

            # 2 job links extracted (unsubscribe dropped), 1 saved (VP >= 65; barista 20 dropped)
            assert res == {"extracted": 2, "saved": 1}, res
            assert email_thread.jobs_extracted == 2
            assert email_thread.jobs_saved == 1

            jobs = (await session.execute(
                select(Job).where(Job.source_email_id == et_id)
            )).scalars().all()
            assert len(jobs) == 1
            j = jobs[0]
            assert j.source == JobSource.gmail_alert
            assert j.role == "VP Product"
            assert j.s1 == 90
            assert j.portal_url == "https://careers.x.com/jobs/1-vp-product"
    finally:
        async with Session() as session:
            await session.execute(delete(Job).where(Job.source_email_id == et_id))
            await session.execute(delete(EmailThread).where(EmailThread.id == et_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()

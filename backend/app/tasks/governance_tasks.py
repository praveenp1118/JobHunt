"""Governance Celery tasks — purge accounts past their 30-day deletion grace window."""
import asyncio
import logging

from app.worker import celery_app

logger = logging.getLogger("jobhunt.governance")


@celery_app.task(name="tasks.purge_deleted_accounts", bind=True)
def purge_deleted_accounts(self):
    from app.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_purge_async())
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


async def _purge_async():
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserCredentials

    purged = []
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        due = (await session.execute(
            select(User).where(
                User.data_deletion_scheduled_at.isnot(None),
                User.data_deletion_scheduled_at < now,
            )
        )).scalars().all()

        for user in due:
            uid = str(user.id)
            # 1) Best-effort: delete the user's local storage (PDFs, attachments).
            try:
                import shutil
                from app.config import settings
                base = getattr(settings, "storage_path", "/app/storage")
                shutil.rmtree(f"{base}/{uid}", ignore_errors=True)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"purge storage failed for {uid}: {e}")

            # 2) Best-effort: stop the user's billing at their payment provider. Razorpay
            #    has no "delete customer" like Stripe — cancelling the subscription
            #    immediately (at_cycle_end=False) is the cleanup, since the account is
            #    being purged. A provider error must not block the purge.
            try:
                from app.utils.razorpay_client import is_razorpay_user, cancel_razorpay_subscription
                if is_razorpay_user(user):
                    await asyncio.to_thread(
                        cancel_razorpay_subscription, user.razorpay_subscription_id, False)
                elif user.stripe_customer_id:
                    import stripe
                    from app.config import settings
                    stripe.api_key = settings.stripe_secret_key
                    await asyncio.to_thread(stripe.Customer.delete, user.stripe_customer_id)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"purge provider cleanup failed for {uid}: {e}")

            # 3) Delete the User row — ON DELETE CASCADE removes CVs, jobs, tailored CVs,
            #    chat, career, usage logs, rate-limit logs, credentials, etc. audit_logs.user_id
            #    is SET NULL so the security trail survives anonymised.
            await session.delete(user)
            purged.append(uid)

        await session.commit()

    logger.warning(f"purge_deleted_accounts: purged {len(purged)} account(s)")
    return {"purged": len(purged), "user_ids": purged}

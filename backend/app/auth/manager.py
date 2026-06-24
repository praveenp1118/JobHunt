import uuid
from typing import Optional
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User, UserCredentials, UserPreferences, UserRole
from app.models.wallet import Wallet, WalletTransaction


async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """
        Runs after every new user registration.
        - Promotes first user / admin email to admin role
        - Creates wallet with ₹20 starter gift
        - Creates UserCredentials and UserPreferences
        """
        session: AsyncSession = self.user_db.session

        # ── Promote to admin if first user or admin email ──────────────────
        result = await session.execute(select(func.count(User.id)))
        user_count = result.scalar_one()

        if user_count == 1 or user.email == settings.admin_email:
            await session.execute(
                User.__table__.update()
                .where(User.id == user.id)
                .values(role=UserRole.admin)
            )

        # ── Wallet with ₹20 starter gift ───────────────────────────────────
        wallet = Wallet(user_id=user.id, balance_paise=2000)
        session.add(wallet)
        await session.flush()

        txn = WalletTransaction(
            wallet_id=wallet.id,
            user_id=user.id,
            transaction_type="gift",
            description="Welcome gift on signup",
            amount_paise=2000,
            balance_after_paise=2000,
        )
        session.add(txn)

        # ── Credentials (empty — user fills in Settings) ───────────────────
        creds = UserCredentials(user_id=user.id)
        session.add(creds)

        # ── Default preferences ────────────────────────────────────────────
        prefs = UserPreferences(user_id=user.id)
        session.add(prefs)

        await session.commit()
        print(f"✅ New user registered: {user.email}")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Send password reset email."""
        from app.utils.email import send_password_reset_email
        await send_password_reset_email(user.email, token)
        print(f"📧 Password reset token sent to {user.email}")

    async def on_after_reset_password(self, user: User, request: Optional[Request] = None):
        print(f"✅ Password reset for {user.email}")

    async def on_after_verify(self, user: User, request: Optional[Request] = None):
        print(f"✅ Email verified for {user.email}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        from app.utils.email import send_verification_email
        await send_verification_email(user.email, token)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)

import uuid
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

from app.config import settings
from app.models.user import User
from app.auth.manager import get_user_manager


# ── JWT Strategies ────────────────────────────────────────────────────────────

def get_jwt_strategy() -> JWTStrategy:
    """Standard 7-day token."""
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.jwt_expire_days * 86400,
        algorithm=settings.jwt_algorithm,
    )


def get_jwt_strategy_long() -> JWTStrategy:
    """30-day token for Remember Me."""
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.jwt_expire_days_remember_me * 86400,
        algorithm=settings.jwt_algorithm,
    )


# ── Transport ─────────────────────────────────────────────────────────────────
bearer_transport = BearerTransport(tokenUrl="/api/auth/login")


# ── Auth Backends ─────────────────────────────────────────────────────────────
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

auth_backend_long = AuthenticationBackend(
    name="jwt-long",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy_long,
)


# ── FastAPI-Users instance ────────────────────────────────────────────────────
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend, auth_backend_long],
)


# ── Google OAuth client ───────────────────────────────────────────────────────
google_oauth_client = None

if settings.google_client_id and settings.google_client_secret:
    try:
        from httpx_oauth.clients.google import GoogleOAuth2
        google_oauth_client = GoogleOAuth2(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        print("✅ Google OAuth configured")
    except Exception as e:
        print(f"⚠️  Google OAuth not configured: {e}")

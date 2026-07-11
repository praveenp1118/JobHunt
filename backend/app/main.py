from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import engine, get_db
from app.auth.dependencies import require_admin, current_active_user
from app.models.user import User


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 JobHunt starting in {settings.env} mode")
    yield
    await engine.dispose()
    print("🛑 JobHunt shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AIJobsHunt API",
    description="AIJobsHunt — AI job co-pilot for every professional field",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    swagger_ui_init_oauth={},
)

# Add HTTPBearer to OpenAPI so Swagger Authorize works with plain tokens
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["components"]["securitySchemes"]["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
    }
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# ── Security headers ──────────────────────────────────────────────────────────
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("jobhunt")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Remaining"],
)


# ── Global error handler — never leak internals ───────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again or contact support.",
                 "code": "internal_error"},
    )

# ── Auth routers ──────────────────────────────────────────────────────────────
from app.auth.config import fastapi_users, auth_backend, auth_backend_long, google_oauth_client
from app.schemas.user import UserRead, UserCreate, UserUpdate
from app.routers.auth import router as auth_router

# FastAPI-Users built-in routes (register, verify, forgot-password, reset-password)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/api/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/api/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/api/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/api/users",
    tags=["users"],
)

# Google OAuth (only if configured)
if google_oauth_client:
    app.include_router(
        fastapi_users.get_oauth_router(
            google_oauth_client,
            auth_backend,
            settings.secret_key,
            redirect_url=f"{settings.frontend_url}/auth/google/callback",
            associate_by_email=True,  # merge accounts with same email
        ),
        prefix="/api/auth/google",
        tags=["auth"],
    )

# Custom auth routes (login with remember_me, profile, credentials, preferences, admin)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# ── Other routers (added in future phases) ────────────────────────────────────
from app.routers.cvs import router as cvs_router
app.include_router(cvs_router, prefix="/api/cvs", tags=["cvs"])

from app.routers.jobs import router as jobs_router
app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])

from app.routers.tailor import router as tailor_router
app.include_router(tailor_router, prefix="/api/tailor", tags=["tailor"])

from app.routers.gmail import router as gmail_router
app.include_router(gmail_router, prefix="/api/gmail", tags=["gmail"])

from app.routers.feeds import router as feeds_router
app.include_router(feeds_router, prefix="/api", tags=["feeds"])

from app.routers.wallet import router as wallet_router
app.include_router(wallet_router, prefix="/api/wallet", tags=["wallet"])

from app.routers.pdfs import router as pdfs_router
app.include_router(pdfs_router, prefix="/api/pdfs", tags=["pdfs"])

from app.routers.activity import router as activity_router
app.include_router(activity_router, prefix="/api/activity", tags=["activity"])

from app.routers.billing import router as billing_router
app.include_router(billing_router, prefix="/api/billing", tags=["billing"])

from app.routers.chat import router as chat_router, chat_websocket
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.add_api_websocket_route("/ws/chat/{conversation_id}", chat_websocket)

from app.routers.usage import router as usage_router
app.include_router(usage_router, prefix="/api/usage", tags=["usage"])

from app.routers.community import router as community_router
app.include_router(community_router, prefix="/api/community", tags=["community"])

from app.routers.career import router as career_router
app.include_router(career_router, prefix="/api/career", tags=["career"])

from app.routers.templates import router as templates_router
app.include_router(templates_router, prefix="/api/templates", tags=["templates"])

from app.routers.privacy import router as privacy_router
app.include_router(privacy_router, prefix="/api/privacy", tags=["privacy"])

from app.routers.scoring import router as scoring_router
app.include_router(scoring_router, prefix="/api/scoring", tags=["scoring"])

from app.routers.access import router as access_router
app.include_router(access_router, prefix="/api", tags=["access"])

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "env": settings.env,
        "version": "1.0.0",
        "google_oauth": google_oauth_client is not None,
    }


@app.get("/")
async def root():
    return {"message": "AIJobsHunt API — see /api/docs"}


# ── Send-mode visibility ──────────────────────────────────────────────────────
@app.get("/api/settings/mode")
async def settings_mode(
    user: User = Depends(current_active_user),
    session=Depends(get_db),
):
    """Where will an outgoing application email actually go? In test mode every email
    is redirected to the user's notification address; in production it goes to the
    real recruiter. The Email Draft tab surfaces this so there are no surprises."""
    from sqlalchemy import select
    from app.models.user import UserCredentials

    creds = (await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )).scalar_one_or_none()
    notification_email = (
        (creds.notification_email if creds and creds.notification_email else None)
        or settings.notification_email
        or user.email
    )
    return {
        "mode": "production" if settings.is_production else "test",
        "notification_email": notification_email,
    }


@app.get("/api/settings/legal-urls")
async def legal_urls():
    """Public — the hosted Privacy / Terms / Cookies page URLs (for footer + auth pages)."""
    return {
        "privacy_url": settings.privacy_policy_url,
        "terms_url": settings.terms_url,
        "cookies_url": settings.cookies_url,
    }

# ── Admin stats endpoint ──────────────────────────────────────────────────────
@app.get("/api/admin/stats")
async def admin_stats(
    session=Depends(get_db),
    admin: User = Depends(require_admin),
):
    from sqlalchemy import func, select
    from app.models.user import User
    from app.models.job import Job, JobStatus
    from app.models.cv import DomainCV, TailoredCV
    
    async with session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar()
        active_users = (await session.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
        total_jobs = (await session.execute(select(func.count(Job.id)))).scalar()
        total_applied = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.applied))).scalar()
        total_domain_cvs = (await session.execute(select(func.count(DomainCV.id)))).scalar()
        total_tailored = (await session.execute(select(func.count(TailoredCV.id)))).scalar()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_jobs": total_jobs,
        "total_applied": total_applied,
        "total_domain_cvs": total_domain_cvs,
        "total_tailored": total_tailored,
    }


# ── Admin governance dashboard ────────────────────────────────────────────────
@app.get("/api/admin/governance")
async def admin_governance(session=Depends(get_db), admin: User = Depends(require_admin)):
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func, select
    from app.models.user import User as U
    from app.models.governance import AuditLog

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def _count(action, since):
        return (await session.execute(select(func.count(AuditLog.id)).where(
            AuditLog.action == action, AuditLog.created_at >= since))).scalar() or 0

    logs = (await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))).scalars().all()
    pending = (await session.execute(
        select(U).where(U.data_deletion_scheduled_at.isnot(None)))).scalars().all()

    return {
        "audit_events_today": await _count_any(session, midnight),
        "rate_limit_violations": await _count("rate_limit_exceeded", midnight),
        "failed_logins": await _count("login_failure", day_ago),
        "data_exports_today": await _count("export_data", midnight),
        "hallucination_violations": await _count("hallucination_flagged", week_ago),
        "pending_deletions": [
            {"user_id": str(u.id), "email": u.email,
             "scheduled_at": u.data_deletion_scheduled_at.isoformat() if u.data_deletion_scheduled_at else None}
            for u in pending
        ],
        "audit_logs": [
            {"id": str(l.id), "user_id": str(l.user_id) if l.user_id else None, "action": l.action,
             "ip": l.ip_address, "details": l.details,
             "created_at": l.created_at.isoformat() if l.created_at else None}
            for l in logs
        ],
    }


async def _count_any(session, since):
    from sqlalchemy import func, select
    from app.models.governance import AuditLog
    return (await session.execute(select(func.count(AuditLog.id)).where(
        AuditLog.created_at >= since))).scalar() or 0


@app.post("/api/admin/governance/cancel-deletion/{user_id}")
async def admin_cancel_deletion(user_id: str, session=Depends(get_db), admin: User = Depends(require_admin)):
    """Admin override — clear a user's scheduled deletion."""
    import uuid as _uuid
    from sqlalchemy import select
    from app.models.user import User as U
    u = (await session.execute(select(U).where(U.id == _uuid.UUID(user_id)))).scalar_one_or_none()
    if not u:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    u.data_deletion_requested_at = None
    u.data_deletion_scheduled_at = None
    await session.commit()
    return {"cancelled": True}

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import engine, get_db
from app.auth.dependencies import require_admin
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
    title="JobHunt API",
    description="AI-powered job search platform for senior product leaders",
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

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {"message": "JobHunt API — see /api/docs"}

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

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    env: str = "development"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    postgres_db: str = "jobhunt"
    postgres_user: str = "jobhunt"
    postgres_password: str

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── Auth ──────────────────────────────────────────────────────────────────
    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    jwt_expire_days_remember_me: int = 30

    # ── Google OAuth ──────────────────────────────────────────────────────────
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:3000/auth/google/callback"

    # ── Admin seed ────────────────────────────────────────────────────────────
    admin_email: str
    admin_initial_password: str

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"
    platform_anthropic_api_key: Optional[str] = None

    # ── Apify ─────────────────────────────────────────────────────────────────
    apify_token: Optional[str] = None
    platform_apify_token: Optional[str] = None

    # ── Gmail ─────────────────────────────────────────────────────────────────
    gmail_address: Optional[str] = None
    gmail_app_password: Optional[str] = None
    notification_email: Optional[str] = None

    # ── Encryption ────────────────────────────────────────────────────────────
    fernet_key: str

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_backend: str = "local"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_s3_bucket: Optional[str] = None
    aws_region: str = "ap-south-1"

    # ── Razorpay (JobHunt Pro subscription — parallel to Stripe, TEST keys only) ─
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None
    razorpay_plan_id: Optional[str] = None

    # Which billing provider the frontend uses: 'stripe' | 'razorpay'. Stays 'stripe'
    # until Razorpay is approved + E2E-tested, then flip (no frontend redeploy needed).
    payment_provider: str = "stripe"

    # ── Stripe (JobHunt Pro subscription) ─────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_pro_price_id: str = ""
    stripe_webhook_secret: str = ""

    # ── Legal pages (GitHub Pages, served from /docs) ─────────────────────────
    privacy_policy_url: str = "https://aijobshunt.com/privacy"
    terms_url: str = "https://aijobshunt.com/terms"
    cookies_url: str = "https://aijobshunt.com/cookies"

    # ── Scoring thresholds ────────────────────────────────────────────────────
    s1_min_threshold: int = 65
    s3_block_threshold: int = 85
    s3_review_threshold: int = 90

    # ── Scheduler ─────────────────────────────────────────────────────────────
    weekly_scan_cron: str = "30 17 * * 0"
    gmail_poll_interval_minutes: int = 60
    ghost_after_days: int = 28

    # ── Auto-enrich cron (high-scoring partial-JD jobs via Bright Data) ────────
    partial_enrich_enabled: bool = True         # global kill-switch
    partial_enrich_cap: int = 20                # HARD ceiling per user per run
    partial_enrich_cron: str = "0 3 * * *"      # daily 03:00 UTC (08:30 IST) — free slot

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def sync_database_url(self) -> str:
        """Sync version for Alembic migrations."""
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql://"
        )


settings = Settings()

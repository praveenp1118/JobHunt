import uuid
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class FeedRead(BaseModel):
    id: uuid.UUID
    feed_type: str
    name: str
    url_or_actor: str
    is_active: bool
    is_platform: bool
    keywords: Optional[str]
    location: Optional[str]
    date_range_days: int
    created_at: datetime
    actor_name: Optional[str] = None  # Apify actor display name (for apify feeds)
    # V2: domain-CV-linked feed profiles (consumed by FeedsTab "Domain CV feed profiles")
    domain_cv_id: Optional[uuid.UUID] = None
    search_keywords: Optional[str] = None
    job_boards: Optional[str] = None  # JSON string, parsed client-side
    is_auto_generated: bool = False
    provider_config: Optional[dict] = None  # Phase 2: Bright Data feed filters

    class Config:
        from_attributes = True


class FeedCreate(BaseModel):
    feed_type: str  # rss | apify | brightdata
    name: str
    url_or_actor: str  # brightdata: sub-source ('linkedin'|'indeed')
    actor_name: Optional[str] = None  # human-readable Apify actor name (from Store picker)
    keywords: Optional[str] = None
    location: Optional[str] = None
    date_range_days: int = 7
    # V2: link a manually-added feed to the domain CV it was built from
    domain_cv_id: Optional[uuid.UUID] = None
    search_keywords: Optional[str] = None
    provider_config: Optional[dict] = None  # Phase 2: Bright Data filters (country, experience_level, …)


# ── V2: domain-CV-driven "Add feed" modal ────────────────────────────────────

class FeedSuggestRequest(BaseModel):
    domain_cv_id: uuid.UUID


class BoardOption(BaseModel):
    name: str
    url: str                 # keywords already substituted, ready to use
    url_template: str        # raw template with {keywords} for client re-substitution


class ApifyActorOption(BaseModel):
    name: str
    actor_id: str


class FeedSuggestion(BaseModel):
    domain_cv_id: uuid.UUID
    feed_name: str
    search_keywords: str
    rss_boards: list[BoardOption]
    apify_actors: list[ApifyActorOption]
    tokens_used: Optional[int] = None
    cost_inr: Optional[float] = None


class ApifyStoreActor(BaseModel):
    id: str            # actor id — stored as the feed's url_or_actor
    name: str
    description: str = ""
    runs: int = 0      # stats.totalRuns — popularity indicator


class FeedUpdate(BaseModel):
    name: Optional[str] = None
    url_or_actor: Optional[str] = None   # ignored for platform feeds (managed)
    keywords: Optional[str] = None
    search_keywords: Optional[str] = None
    location: Optional[str] = None
    date_range_days: Optional[int] = None
    is_active: Optional[bool] = None
    domain_cv_id: Optional[uuid.UUID] = None
    provider_config: Optional[dict] = None


class ScanResult(BaseModel):
    started_at: datetime
    status: str
    jobs_found: int
    jobs_added: int
    errors: list[str] = []


class TargetCompanyRead(BaseModel):
    id: uuid.UUID
    company_name: str
    career_page_url: Optional[str]
    market: Optional[str]
    is_active: bool
    is_platform: bool

    class Config:
        from_attributes = True


class TargetCompanyCreate(BaseModel):
    company_name: str
    career_page_url: Optional[str] = None
    market: Optional[str] = None

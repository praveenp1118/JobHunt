import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from app.models.job import JobStatus, JobSource, EmailDirection, EmailClassification


# ── Job schemas ───────────────────────────────────────────────────────────────

class JobRead(BaseModel):
    id: uuid.UUID
    company: str
    role: str
    location: Optional[str]
    market: Optional[str]
    jd_language: str
    jd_raw: Optional[str] = None       # full scraped JD text (JD tab)
    jd_md: Optional[str] = None
    has_partial_jd: bool = False       # JD is only an alert-email snippet
    source: JobSource
    status: JobStatus
    s1: Optional[float]
    s1d: Optional[float] = None
    s2: Optional[float]
    s3_domain: Optional[float]
    s3_master: Optional[float]
    recruiter_email: Optional[str]
    portal_url: Optional[str]
    salary_range_raw: Optional[str]
    needs_hitl: bool
    applied_at: Optional[datetime]
    interview_date: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    # V3: multi-domain-CV scoring (drives Tailor pre-select + per-option scores)
    detected_domain_cv_id: Optional[uuid.UUID] = None
    domain_cv_scores: Optional[dict] = None
    best_domain_cv_id: Optional[uuid.UUID] = None

    # Populated from related records
    industry_label: Optional[str] = None
    function_label: Optional[str] = None
    domain_cv_label: Optional[str] = None

    class Config:
        from_attributes = True


class JobSummary(BaseModel):
    """Lighter version for tracker table."""
    id: uuid.UUID
    company: str
    role: str
    market: Optional[str]
    source: JobSource
    status: JobStatus
    s1: Optional[float]
    s1d: Optional[float] = None              # best domain CV fit
    s2: Optional[float]
    s3_master: Optional[float]
    needs_hitl: bool
    has_partial_jd: bool = False  # JD is only an alert-email snippet; full JD behind portal_url
    detected_domain_cv_id: Optional[uuid.UUID] = None  # V2/V3: feed/alert domain match (frontend maps to label)
    # V3: fit against ALL active domain CVs at ingestion ({domain_cv_id: score})
    domain_cv_scores: Optional[dict] = None
    best_domain_cv_id: Optional[uuid.UUID] = None      # highest-scoring domain CV
    # {domain_cv_id: "Industry × Country"} — enriched in the list endpoint
    domain_cv_labels: Optional[dict] = None
    applied_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class JobFromText(BaseModel):
    """Manual paste — raw JD text."""
    raw_text: str
    score_immediately: bool = True


class JobFromURL(BaseModel):
    """Fetch from URL."""
    url: str
    score_immediately: bool = True


class JobConfirm(BaseModel):
    """
    After parsing, user can edit fields before saving.
    Company and role are required minimum.
    """
    company: str
    role: str
    location: Optional[str] = None
    market: Optional[str] = None
    recruiter_email: Optional[str] = None
    portal_url: Optional[str] = None
    jd_md: Optional[str] = None  # edited JD text
    notes: Optional[str] = None


class JobStatusUpdate(BaseModel):
    status: JobStatus
    notes: Optional[str] = None


class JobUpdate(BaseModel):
    recruiter_email: Optional[str] = None
    portal_url: Optional[str] = None
    notes: Optional[str] = None
    salary_expectation: Optional[str] = None
    interview_date: Optional[datetime] = None
    interview_link: Optional[str] = None
    interview_format: Optional[str] = None
    interviewer_name: Optional[str] = None
    interviewer_email: Optional[str] = None
    offer_amount: Optional[str] = None
    offer_currency: Optional[str] = None


# ── Parse result (returned before save, user can edit) ───────────────────────

class JDParseResult(BaseModel):
    """What comes back from parse — user can edit before confirming save."""
    # Temp key (not saved yet)
    temp_id: str

    # Parsed fields
    company: str
    role: str
    location: Optional[str]
    market: Optional[str]
    seniority: Optional[str]
    remote_policy: Optional[str]
    required_skills: List[str]
    preferred_skills: List[str]
    comp_range: Optional[str]
    recruiter_email: Optional[str]
    jd_language: str

    # Scoring
    s1_score: float
    key_matches: List[str]
    gaps: List[str]

    # Pre-filter result
    pre_filter_passed: bool
    pre_filter_reason: Optional[str] = None

    # Dedup flag
    is_duplicate: bool = False
    existing_job_id: Optional[uuid.UUID] = None

    # Usage for this parse (None if not scored)
    s1_tokens: Optional[int] = None
    s1_cost_inr: Optional[float] = None


# ── Email thread ──────────────────────────────────────────────────────────────

class EmailThreadRead(BaseModel):
    id: uuid.UUID
    direction: EmailDirection
    classification: Optional[EmailClassification]
    subject: Optional[str]
    from_email: Optional[str]
    to_email: Optional[str]
    body_preview: Optional[str]
    cv_pdf_attached: bool
    cl_pdf_attached: bool
    needs_hitl: bool
    sent_at: Optional[datetime]
    received_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Filters for tracker ───────────────────────────────────────────────────────

class JobFilters(BaseModel):
    status: Optional[List[JobStatus]] = None
    market: Optional[List[str]] = None
    source: Optional[List[JobSource]] = None
    search: Optional[str] = None
    needs_hitl: Optional[bool] = None
    min_s1: Optional[float] = None

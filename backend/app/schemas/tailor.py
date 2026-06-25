import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from app.models.cv import ChangeType, ChangeStatus


class TailorRequest(BaseModel):
    """Start the tailor flow for a job."""
    job_id: uuid.UUID
    domain_cv_id: uuid.UUID


class TailorPackageRead(BaseModel):
    """What comes back from the generate step."""
    tailored_cv_id: uuid.UUID
    s2_score: float
    s2_key_matches: List[str]
    changelog: List[dict]
    cover_letter_md: str
    email_draft: str
    cl_template_used: str
    tokens_used: Optional[int] = None
    cost_inr: Optional[float] = None


class TailorChangeRead(BaseModel):
    id: uuid.UUID
    change_type: ChangeType
    section: Optional[str]
    original_text: Optional[str]
    proposed_text: Optional[str]
    final_text: Optional[str]
    reason: Optional[str]
    status: ChangeStatus

    class Config:
        from_attributes = True


class TailorApplyResult(BaseModel):
    """After Generate button — approved changes applied, S3 computed."""
    tailored_cv_id: uuid.UUID
    tailored_cv_md: str
    cover_letter_md: str
    email_draft: str
    s2_score: float
    s3_domain: float
    s3_master: float
    s3_status: str  # green | amber | blocked
    s3_flags: List[str]
    cl_template_used: str
    tokens_used: Optional[int] = None
    cost_inr: Optional[float] = None
    session_tokens: Optional[int] = None
    session_cost_inr: Optional[float] = None
    overflow: Optional[dict] = None  # page-budget check vs the user's CV template
    hallucination_check: Optional[dict] = None  # {valid, violations} — invented-metric guard


class RegenerateCLRequest(BaseModel):
    exclude_template: Optional[str] = None


class FollowUpRequest(BaseModel):
    context: Optional[str] = None


class ApplyMethodRequest(BaseModel):
    method: str  # "email" | "portal"
    recruiter_email: Optional[str] = None
    include_cover_letter: bool = True

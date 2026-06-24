import uuid
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.models.cv import CVStatus, ChangeType, ChangeStatus


# ── Master CV ─────────────────────────────────────────────────────────────────

class MasterCVRead(BaseModel):
    id: uuid.UUID
    content_md: str
    version: int
    word_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MasterCVVersionRead(BaseModel):
    id: uuid.UUID
    version: int
    change_summary: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MasterCVUpdate(BaseModel):
    content_md: str
    change_summary: Optional[str] = None


# ── Domain CV ─────────────────────────────────────────────────────────────────

class DomainCVCreate(BaseModel):
    industry_id: uuid.UUID
    function_id: uuid.UUID
    country_code: str


class DomainCVRead(BaseModel):
    id: uuid.UUID
    industry_id: uuid.UUID
    function_id: uuid.UUID
    country_code: str
    content_md: str
    version: int
    status: CVStatus
    s3_domain: Optional[float]
    s3_master: Optional[float]
    created_at: datetime
    updated_at: datetime

    # Computed display fields
    industry_label: Optional[str] = None
    function_label: Optional[str] = None
    country_name: Optional[str] = None

    class Config:
        from_attributes = True


class DomainCVVersionRead(BaseModel):
    id: uuid.UUID
    version: int
    s3_domain: Optional[float]
    s3_master: Optional[float]
    change_summary: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Change log ────────────────────────────────────────────────────────────────

class ChangeLogItemRead(BaseModel):
    id: uuid.UUID
    change_type: ChangeType
    section: Optional[str]
    original_text: Optional[str]
    proposed_text: Optional[str]
    final_text: Optional[str]
    reason: Optional[str]
    status: ChangeStatus
    created_at: datetime

    class Config:
        from_attributes = True


class ChangeLogApprove(BaseModel):
    """Approve a change as-is."""
    pass


class ChangeLogEdit(BaseModel):
    """Approve with manual edit."""
    final_text: str


class ChangeLogBulkAction(BaseModel):
    """Bulk approve or reject all pending changes."""
    action: str  # "approve_all" | "reject_all"


# ── S3 score result ───────────────────────────────────────────────────────────

class S3ScoreResult(BaseModel):
    s3_domain: float
    s3_master: float
    flags: list[str] = []
    status: str  # "green" | "amber" | "blocked"

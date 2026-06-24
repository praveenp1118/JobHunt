"""
File storage abstraction.
Local in Phase 4 — swap to S3 in V2 by changing the backend.
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional

STORAGE_ROOT = Path("/app/storage")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


async def save_text_file(content: str, relative_path: str) -> str:
    """Save text content to storage. Returns the relative path."""
    full_path = STORAGE_ROOT / relative_path
    _ensure_dir(full_path.parent)
    async with aiofiles.open(full_path, "w", encoding="utf-8") as f:
        await f.write(content)
    return relative_path


async def read_text_file(relative_path: str) -> Optional[str]:
    """Read text content from storage. Returns None if not found."""
    full_path = STORAGE_ROOT / relative_path
    if not full_path.exists():
        return None
    async with aiofiles.open(full_path, "r", encoding="utf-8") as f:
        return await f.read()


async def save_binary_file(content: bytes, relative_path: str) -> str:
    """Save binary content (PDF etc.) to storage."""
    full_path = STORAGE_ROOT / relative_path
    _ensure_dir(full_path.parent)
    async with aiofiles.open(full_path, "wb") as f:
        await f.write(content)
    return relative_path


async def delete_file(relative_path: str) -> None:
    """Delete a file from storage."""
    full_path = STORAGE_ROOT / relative_path
    if full_path.exists():
        full_path.unlink()


def cv_master_path(user_id: uuid.UUID, version: int) -> str:
    return f"cvs/{user_id}/master/v{version}.md"


def cv_domain_path(user_id: uuid.UUID, domain_cv_id: uuid.UUID, version: int) -> str:
    return f"cvs/{user_id}/domains/{domain_cv_id}/v{version}.md"


def cv_tailored_path(user_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"cvs/{user_id}/tailored/{job_id}/cv.md"


def cl_tailored_path(user_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"cvs/{user_id}/tailored/{job_id}/cl.md"


def cv_pdf_path(user_id: uuid.UUID, filename: str) -> str:
    return f"pdfs/{user_id}/{filename}"

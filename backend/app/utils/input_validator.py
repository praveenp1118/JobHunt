"""Input validation + sanitisation helpers."""
import re
import uuid

from bs4 import BeautifulSoup

CV_ALLOWED_TYPES = ["pdf", "docx", "doc", "md", "txt"]
CHAT_ALLOWED_TYPES = ["pdf", "docx", "png", "jpg", "jpeg", "gif", "webp"]
MAX_CV_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_CHAT_SIZE = 5 * 1024 * 1024  # 5 MB

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def sanitize_text(text: str, max_length: int) -> str:
    """Strip HTML tags and clamp length."""
    if not text:
        return ""
    clean = BeautifulSoup(text, "html.parser").get_text()
    return clean[:max_length].strip()


def validate_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def validate_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email))


def validate_file_type(filename: str, allowed: list) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in allowed

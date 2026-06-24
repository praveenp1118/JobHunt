"""
Fernet symmetric encryption for stored credentials.
All API keys and passwords encrypted at rest.
"""
from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.fernet_key.encode())


def encrypt(value: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext."""
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    return _fernet.decrypt(value.encode()).decode()


def encrypt_if_present(value: str | None) -> str | None:
    if value is None:
        return None
    return encrypt(value)


def decrypt_if_present(value: str | None) -> str | None:
    if value is None:
        return None
    return decrypt(value)

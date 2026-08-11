"""Password hashing + signed session cookie for the single-owner admin site.

No Supabase Auth / multi-user session store here on purpose - there is
exactly one admin, so a signed cookie is the whole auth system.
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.context import CryptContext

from app.config import settings

SESSION_COOKIE_NAME = "admin_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_signer = TimestampSigner(settings.admin_session_secret)


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return _pwd_context.verify(password, password_hash)


def create_session_cookie() -> str:
    return _signer.sign(settings.admin_username).decode("utf-8")


def is_valid_session_cookie(value: str | None) -> bool:
    if not value:
        return False
    try:
        _signer.unsign(value, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False

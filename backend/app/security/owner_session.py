"""Signed anonymous owner sessions used to scope API database sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from ..core.config import get_settings

_development_secret = secrets.token_bytes(32)
_SESSION_SECONDS = 7 * 24 * 60 * 60


def _sign(owner_id: str, expires_at: int, secret: bytes) -> str:
    payload = f"{owner_id}.{expires_at}"
    digest = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"{payload}.{signature}"


def _secret() -> bytes:
    configured = get_settings().SESSION_SIGNING_SECRET.get_secret_value()
    return configured.encode("utf-8") if configured else _development_secret


def get_or_create_owner_id(cookie_value: str | None) -> tuple[str, str]:
    secret = _secret()
    if cookie_value:
        try:
            owner_id, expires_text, supplied_signature = cookie_value.split(".", 2)
            expires_at = int(expires_text)
            now = int(time.time())
            expected = _sign(owner_id, expires_at, secret).split(".", 2)[2]
            if (len(owner_id) == 64 and now < expires_at <= now + _SESSION_SECONDS and
                    secrets.compare_digest(supplied_signature, expected)):
                return owner_id, _sign(owner_id, now + _SESSION_SECONDS, secret)
        except (ValueError, UnicodeError):
            pass
    owner_id = secrets.token_hex(32)
    return owner_id, _sign(owner_id, int(time.time()) + _SESSION_SECONDS, secret)

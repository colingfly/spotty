# backend/extensions.py
"""Flask extensions that blueprints import before the app exists."""
from __future__ import annotations

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import settings


def _rate_key() -> str:
    """Limit per signed-in user when we can, per IP otherwise."""
    from services.auth_tokens import current_user_id

    sid = current_user_id()
    return f"user:{sid}" if sid else f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=_rate_key,
    default_limits=[settings.rate_limit_default],
    storage_uri="memory://",
    headers_enabled=True,
)

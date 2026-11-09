# backend/services/auth_tokens.py
"""
Stateless bearer tokens for the frontend.

Before this module every endpoint trusted a `spotify_user_id` query param,
so anyone could read or delete another user's library by guessing an id.
Now the OAuth callback issues a signed token that encodes the Spotify user
id; every /api/* route requires it via `require_user`.

Audio URLs are a special case: <audio src> can't send headers, so audio
links carry their own signed token bound to the generation id.
"""
from __future__ import annotations

import functools
import secrets
from typing import Callable, Optional

from flask import g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import settings

_session_serializer = URLSafeTimedSerializer(settings.secret_key, salt="trill.session.v1")
_audio_serializer = URLSafeTimedSerializer(settings.secret_key, salt="trill.audio.v1")
_state_serializer = URLSafeTimedSerializer(settings.secret_key, salt="trill.oauth-state.v1")


# --- session tokens -------------------------------------------------------

def issue_session_token(spotify_user_id: str) -> str:
    return _session_serializer.dumps({"sid": spotify_user_id, "n": secrets.token_hex(4)})


def verify_session_token(token: str) -> Optional[str]:
    try:
        data = _session_serializer.loads(token, max_age=settings.session_ttl_seconds)
    except (BadSignature, SignatureExpired):
        return None
    sid = data.get("sid") if isinstance(data, dict) else None
    return sid or None


def _token_from_request() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    # Allowed for direct links that can't set headers.
    return request.args.get("t") or None


def current_user_id() -> Optional[str]:
    token = _token_from_request()
    if not token:
        return None
    return verify_session_token(token)


def require_user(fn: Callable) -> Callable:
    """Decorator: 401 unless a valid session token is present. Sets g.sid."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        sid = current_user_id()
        if not sid:
            return {"error": "unauthorized", "message": "Sign in with Spotify to continue."}, 401
        g.sid = sid
        return fn(*args, **kwargs)

    return wrapper


# --- audio tokens ---------------------------------------------------------

def sign_audio(generation_id: int) -> str:
    return _audio_serializer.dumps({"g": int(generation_id)})


def verify_audio(token: str, generation_id: int) -> bool:
    try:
        data = _audio_serializer.loads(token)  # audio links do not expire
    except BadSignature:
        return False
    return isinstance(data, dict) and data.get("g") == int(generation_id)


def audio_url_for(generation_id: int) -> str:
    return f"/api/audio/{generation_id}?t={sign_audio(generation_id)}"


# --- oauth state ----------------------------------------------------------

def issue_oauth_state(next_path: str = "/") -> str:
    return _state_serializer.dumps({"n": secrets.token_hex(8), "next": next_path})


def verify_oauth_state(state: str, max_age: int = 600) -> Optional[dict]:
    try:
        data = _state_serializer.loads(state, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None

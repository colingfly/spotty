# backend/routes/auth.py
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from flask import Blueprint, g, redirect, request

from config import settings
from db import SessionLocal
from extensions import limiter
from models import SpotifyAccount
from services.acestep_client import acestep
from services.auth_tokens import (
    issue_oauth_state,
    issue_session_token,
    require_user,
    verify_oauth_state,
)
from services.spotify_client import AUTH_URL, TOKEN_URL, basic_auth_header, fetch_me, refresh_if_needed, spotify_session

log = logging.getLogger("spotty.auth")

auth_bp = Blueprint("auth", __name__)


def _frontend_redirect(fragment: dict) -> str:
    return f"{settings.frontend_url.rstrip('/')}/#{urlencode(fragment)}"


@auth_bp.get("/login")
@limiter.limit("30 per minute")
def login():
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        return {"error": "not_configured", "message": "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET."}, 500
    next_path = request.args.get("next", "/dashboard")
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": settings.spotify_scope,
        "state": issue_oauth_state(next_path),
        "show_dialog": "true" if request.args.get("switch") else "false",
    }
    return redirect(f"{AUTH_URL}?{urlencode(params)}")


@auth_bp.get("/callback")
@limiter.limit("30 per minute")
def callback():
    error = request.args.get("error")
    if error:
        return redirect(_frontend_redirect({"auth_error": error}))

    state = verify_oauth_state(request.args.get("state", ""))
    if state is None:
        return redirect(_frontend_redirect({"auth_error": "invalid_state"}))

    code = request.args.get("code")
    if not code:
        return redirect(_frontend_redirect({"auth_error": "missing_code"}))

    sess = spotify_session()
    r = sess.post(
        TOKEN_URL,
        headers=basic_auth_header(),
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.spotify_redirect_uri},
        timeout=15,
    )
    if r.status_code != 200:
        log.warning("Token exchange failed: %s %s", r.status_code, r.text[:200])
        return redirect(_frontend_redirect({"auth_error": "token_exchange_failed"}))

    tokens = r.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_at = int(time.time()) + int(tokens.get("expires_in", 3600))

    db = SessionLocal()
    try:
        probe = SpotifyAccount(spotify_user_id="", access_token=access_token, expires_at=expires_at)
        try:
            me = fetch_me(probe)
        except Exception as e:
            log.warning("/me failed after login: %s", e)
            return redirect(_frontend_redirect({"auth_error": "profile_failed"}))

        sid = me["id"]
        acct = db.query(SpotifyAccount).filter_by(spotify_user_id=sid).one_or_none()
        if not acct:
            acct = SpotifyAccount(spotify_user_id=sid, access_token=access_token, expires_at=expires_at)
        acct.access_token = access_token
        acct.refresh_token = refresh_token or acct.refresh_token
        acct.expires_at = expires_at
        acct.scope = tokens.get("scope", acct.scope)
        acct.token_type = tokens.get("token_type", acct.token_type)
        acct.display_name = me.get("display_name")
        acct.avatar_url = me.get("avatar_url")
        acct.country = me.get("country")
        acct.product = me.get("product")
        acct.last_login_at = datetime.now(timezone.utc)
        db.add(acct)
        db.commit()
    finally:
        db.close()

    token = issue_session_token(sid)
    return redirect(_frontend_redirect({"token": token, "next": state.get("next") or "/dashboard"}))


@auth_bp.get("/api/me")
@require_user
def me():
    """Who am I + what is the system capable of right now."""
    from services import llm

    db = SessionLocal()
    try:
        acct = db.query(SpotifyAccount).filter_by(spotify_user_id=g.sid).one_or_none()
        if not acct:
            return {"error": "not_linked"}, 404
        needs_reauth = False
        try:
            acct = refresh_if_needed(acct, db)
        except Exception as e:
            log.info("Refresh failed for %s: %s", g.sid, e)
            needs_reauth = True
        return {
            "spotify_user_id": acct.spotify_user_id,
            "display_name": acct.display_name or acct.spotify_user_id,
            "avatar_url": acct.avatar_url,
            "country": acct.country,
            "product": acct.product,
            "needs_reauth": needs_reauth,
            "capabilities": {
                "acestep": acestep.health_check(),
                "llm": llm.status(),
                "max_variations": settings.max_variations,
                "max_duration_seconds": settings.max_duration_seconds,
                "default_duration_seconds": settings.default_duration_seconds,
            },
        }
    finally:
        db.close()


@auth_bp.post("/api/auth/logout")
def logout():
    # Tokens are stateless; the client discards it. Endpoint exists for symmetry/analytics.
    return "", 204

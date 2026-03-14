# backend/routes/auth.py
from __future__ import annotations

import time

from flask import Blueprint, redirect, request
from urllib.parse import urlencode

from config import settings
from db import SessionLocal
from models import SpotifyAccount
from services.spotify_client import (
    AUTH_URL, TOKEN_URL, API_BASE,
    spotify_session, basic_auth_header,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/login")
def login():
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": settings.spotify_scope,
        "show_dialog": "false",
    }
    return redirect(f"{AUTH_URL}?{urlencode(params)}")


@auth_bp.get("/callback")
def callback():
    error = request.args.get("error")
    if error:
        return {"error": error}, 400
    code = request.args.get("code")
    if not code:
        return {"error": "missing_code"}, 400

    sess = spotify_session()
    r = sess.post(
        TOKEN_URL,
        headers=basic_auth_header(),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.spotify_redirect_uri,
        },
    )
    if r.status_code != 200:
        return {"error": "token_exchange_failed", "body": r.text}, r.status_code

    tokens = r.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_at = int(time.time()) + int(tokens.get("expires_in", 3600))

    me = sess.get(
        f"{API_BASE}/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    if me.status_code != 200:
        return {"error": "me_failed", "body": me.text}, me.status_code
    spotify_user_id = me.json()["id"]

    db = SessionLocal()
    try:
        acct = (
            db.query(SpotifyAccount)
            .filter_by(spotify_user_id=spotify_user_id)
            .one_or_none()
        )
        if not acct:
            acct = SpotifyAccount(
                spotify_user_id=spotify_user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=tokens.get("scope"),
                token_type=tokens.get("token_type"),
            )
        else:
            acct.access_token = access_token
            acct.refresh_token = refresh_token or acct.refresh_token
            acct.expires_at = expires_at
            acct.scope = tokens.get("scope", acct.scope)
            acct.token_type = tokens.get("token_type", acct.token_type)

        db.add(acct)
        db.commit()
    finally:
        db.close()

    return redirect(f"{settings.frontend_url}/#sid={spotify_user_id}")

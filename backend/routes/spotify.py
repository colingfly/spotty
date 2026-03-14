# backend/routes/spotify.py
from __future__ import annotations

from flask import Blueprint, request

from config import settings
from db import SessionLocal
from models import SpotifyAccount
from services.spotify_client import (
    API_BASE, spotify_session, refresh_if_needed,
)
from services.taste import get_user_taste, update_user_taste_if_stale

spotify_bp = Blueprint("spotify", __name__)


@spotify_bp.get("/api/me/top-artists")
def api_top_artists():
    sid = request.args.get("spotify_user_id")
    if not sid:
        return {"error": "missing_param", "message": "spotify_user_id is required"}, 400
    time_range = request.args.get("time_range", "medium_term")
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 50)
    except Exception:
        limit = 20

    db = SessionLocal()
    try:
        acct = db.query(SpotifyAccount).filter_by(spotify_user_id=sid).one_or_none()
        if not acct:
            return {"error": "not_linked"}, 404
        try:
            acct = refresh_if_needed(acct, db)
        except Exception as e:
            return {"error": "refresh_failed", "detail": str(e)}, 401

        sess = spotify_session()
        r = sess.get(
            f"{API_BASE}/me/top/artists",
            headers={"Authorization": f"Bearer {acct.access_token}"},
            params={"time_range": time_range, "limit": limit},
        )
        if r.status_code == 401:
            return {"error": "unauthorized"}, 401
        if r.status_code == 403:
            return {"error": "forbidden", "message": "Missing scope user-top-read"}, 403
        if not r.ok:
            return {
                "error": "spotify_error",
                "status_code": r.status_code,
                "body": r.text,
            }, r.status_code

        items = (r.json() or {}).get("items", [])
        artists = [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "genres": a.get("genres", []),
                "popularity": a.get("popularity"),
                "image": (a.get("images") or [{}])[0].get("url"),
                "external_url": a.get("external_urls", {}).get("spotify"),
            }
            for a in items
        ]
        return {
            "items": artists,
            "count": len(artists),
            "limit": limit,
            "time_range": time_range,
        }
    finally:
        db.close()


@spotify_bp.get("/api/me/taste")
def api_taste():
    sid = request.args.get("spotify_user_id")
    if not sid:
        return {"error": "missing_param", "message": "spotify_user_id is required"}, 400

    db = SessionLocal()
    try:
        acct = db.query(SpotifyAccount).filter_by(spotify_user_id=sid).one_or_none()
        if not acct:
            return {"error": "not_linked"}, 404
        try:
            acct = refresh_if_needed(acct, db)
        except Exception as e:
            return {"error": "refresh_failed", "detail": str(e)}, 401

        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
        return {
            "spotify_user_id": ut.spotify_user_id,
            "danceability": ut.danceability,
            "energy": ut.energy,
            "valence": ut.valence,
            "acousticness": ut.acousticness,
            "instrumentalness": ut.instrumentalness,
            "liveness": ut.liveness,
            "speechiness": ut.speechiness,
            "tempo": ut.tempo,
            "genres": ut.genres or [],
            "updated_at": ut.updated_at.isoformat() if ut.updated_at else None,
        }
    finally:
        db.close()

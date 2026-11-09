# backend/routes/spotify.py
from __future__ import annotations

import logging
from collections import Counter

from flask import Blueprint, g, request
from sqlalchemy import func

from config import settings
from db import SessionLocal
from extensions import limiter
from models import Generation, SpotifyAccount
from services.auth_tokens import require_user
from services.spotify_client import TIME_RANGES, SpotifyError, refresh_if_needed, user_top_artists, user_top_tracks
from services.taste import get_or_build_narrative, rebuild_user_taste, taste_payload, update_user_taste_if_stale

log = logging.getLogger("spotty.spotify")

spotify_bp = Blueprint("spotify", __name__)


def _acct(db):
    acct = db.query(SpotifyAccount).filter_by(spotify_user_id=g.sid).one_or_none()
    if not acct:
        return None, ({"error": "not_linked"}, 404)
    try:
        acct = refresh_if_needed(acct, db)
    except Exception as e:
        return None, ({"error": "reauth_required", "message": str(e)}, 401)
    return acct, None


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return min(max(int(request.args.get(name, default)), lo), hi)
    except (TypeError, ValueError):
        return default


@spotify_bp.get("/api/me/top-artists")
@require_user
def api_top_artists():
    time_range = request.args.get("time_range", "medium_term")
    if time_range not in TIME_RANGES:
        time_range = "medium_term"
    limit = _int_arg("limit", 20, 1, 50)

    db = SessionLocal()
    try:
        acct, err = _acct(db)
        if err:
            return err
        try:
            items = user_top_artists(acct, time_range, limit)
        except SpotifyError as e:
            return {"error": "spotify_error", "status_code": e.status}, 502
        return {"items": items, "count": len(items), "limit": limit, "time_range": time_range}
    finally:
        db.close()


@spotify_bp.get("/api/me/top-tracks")
@require_user
def api_top_tracks():
    time_range = request.args.get("time_range", "short_term")
    if time_range not in TIME_RANGES:
        time_range = "short_term"
    limit = _int_arg("limit", 12, 1, 50)

    db = SessionLocal()
    try:
        acct, err = _acct(db)
        if err:
            return err
        items = user_top_tracks(acct, time_range, limit)
        return {"items": items, "count": len(items), "time_range": time_range}
    finally:
        db.close()


@spotify_bp.get("/api/me/taste")
@require_user
def api_taste():
    force = request.args.get("refresh") in ("1", "true")
    db = SessionLocal()
    try:
        acct, err = _acct(db)
        if err:
            return err
        if force:
            try:
                ut = rebuild_user_taste(acct, db)
            except Exception as e:
                return {"error": "taste_unavailable", "message": str(e)}, 502
        else:
            ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
        return taste_payload(ut)
    finally:
        db.close()


@spotify_bp.post("/api/me/taste/refresh")
@require_user
@limiter.limit("4 per minute")
def api_taste_refresh():
    db = SessionLocal()
    try:
        acct, err = _acct(db)
        if err:
            return err
        try:
            ut = rebuild_user_taste(acct, db)
        except Exception as e:
            return {"error": "taste_unavailable", "message": str(e)}, 502
        return taste_payload(ut)
    finally:
        db.close()


@spotify_bp.get("/api/me/insights")
@require_user
@limiter.limit(settings.rate_limit_llm)
def api_insights():
    """Claude-written Sound DNA narrative (cached a week, or until the profile is rebuilt)."""
    force = request.args.get("refresh") in ("1", "true")
    db = SessionLocal()
    try:
        acct, err = _acct(db)
        if err:
            return err
        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
        narrative = get_or_build_narrative(ut, db, force=force)
        from services import llm

        return {
            "narrative": narrative,
            "available": llm.available(),
            "updated_at": ut.narrative_updated_at.isoformat() if ut.narrative_updated_at else None,
        }
    finally:
        db.close()


@spotify_bp.get("/api/me/stats")
@require_user
def api_stats():
    db = SessionLocal()
    try:
        q = db.query(Generation).filter(Generation.spotify_user_id == g.sid)
        total = q.count()
        completed = q.filter(Generation.status == "completed").count()
        favorites = q.filter(Generation.is_favorite == 1).count()
        seconds = db.query(func.coalesce(func.sum(Generation.duration_seconds), 0.0)).filter(
            Generation.spotify_user_id == g.sid, Generation.status == "completed"
        ).scalar() or 0.0
        plays = db.query(func.coalesce(func.sum(Generation.play_count), 0)).filter(
            Generation.spotify_user_id == g.sid
        ).scalar() or 0
        modes = Counter(r[0] for r in db.query(Generation.feature_type).filter(Generation.spotify_user_id == g.sid).all())
        engines = Counter(r[0] or "template" for r in db.query(Generation.engine).filter(Generation.spotify_user_id == g.sid).all())
        return {
            "total": total,
            "completed": completed,
            "favorites": favorites,
            "minutes_generated": round(float(seconds) / 60.0, 1),
            "plays": int(plays),
            "by_mode": dict(modes),
            "by_engine": dict(engines),
        }
    finally:
        db.close()

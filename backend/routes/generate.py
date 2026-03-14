# backend/routes/generate.py
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from flask import Blueprint, request, send_file

from config import settings
from db import SessionLocal
from models import SpotifyAccount, Generation
from services.spotify_client import refresh_if_needed
from services.taste import update_user_taste_if_stale
from services.caption_engine import taste_to_caption
from services.acestep_client import acestep

log = logging.getLogger("spotty.generate")

generate_bp = Blueprint("generate", __name__)


def _get_acct_and_db(sid: str):
    """Helper: look up account, refresh tokens, return (acct, db) or raise."""
    db = SessionLocal()
    acct = db.query(SpotifyAccount).filter_by(spotify_user_id=sid).one_or_none()
    if not acct:
        db.close()
        return None, None
    acct = refresh_if_needed(acct, db)
    return acct, db


# ---------------------------------------------------------------
# POST /api/generate/taste-to-track
# ---------------------------------------------------------------
@generate_bp.post("/api/generate/taste-to-track")
def taste_to_track():
    data = request.get_json(silent=True) or {}
    sid = data.get("spotify_user_id")
    if not sid:
        return {"error": "missing_param", "message": "spotify_user_id is required"}, 400

    acct, db = _get_acct_and_db(sid)
    if not acct:
        return {"error": "not_linked"}, 404

    try:
        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
        overrides = data.get("overrides")
        params = taste_to_caption(ut, overrides=overrides)

        # Check ACE-Step availability
        if not acestep.health_check():
            return {"error": "acestep_unavailable", "message": "ACE-Step server is not running"}, 503

        task_id = acestep.submit_task(params)

        gen = Generation(
            spotify_user_id=sid,
            task_id=task_id,
            status="pending",
            feature_type="taste_to_track",
            caption_used=params.get("prompt"),
            lyrics_used=params.get("lyrics"),
            params_json=params,
        )
        db.add(gen)
        db.commit()
        db.refresh(gen)

        return {
            "generation_id": gen.id,
            "task_id": task_id,
            "status": "pending",
            "caption": params.get("prompt"),
            "params": params,
        }
    except Exception as e:
        log.exception("taste-to-track failed")
        return {"error": "generation_failed", "detail": str(e)}, 500
    finally:
        db.close()


# ---------------------------------------------------------------
# POST /api/generate/custom (mood sliders)
# ---------------------------------------------------------------
@generate_bp.post("/api/generate/custom")
def custom_generate():
    data = request.get_json(silent=True) or {}
    sid = data.get("spotify_user_id")
    if not sid:
        return {"error": "missing_param", "message": "spotify_user_id is required"}, 400

    acct, db = _get_acct_and_db(sid)
    if not acct:
        return {"error": "not_linked"}, 404

    try:
        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
        overrides = data.get("overrides", {})
        params = taste_to_caption(ut, overrides=overrides)

        if not acestep.health_check():
            return {"error": "acestep_unavailable"}, 503

        task_id = acestep.submit_task(params)

        gen = Generation(
            spotify_user_id=sid,
            task_id=task_id,
            status="pending",
            feature_type="mood_slider",
            caption_used=params.get("prompt"),
            lyrics_used=params.get("lyrics"),
            params_json=params,
        )
        db.add(gen)
        db.commit()
        db.refresh(gen)

        return {
            "generation_id": gen.id,
            "task_id": task_id,
            "status": "pending",
            "caption": params.get("prompt"),
            "params": params,
        }
    except Exception as e:
        log.exception("custom generate failed")
        return {"error": "generation_failed", "detail": str(e)}, 500
    finally:
        db.close()


# ---------------------------------------------------------------
# POST /api/generate/lyric-mode
# ---------------------------------------------------------------
@generate_bp.post("/api/generate/lyric-mode")
def lyric_mode():
    data = request.get_json(silent=True) or {}
    sid = data.get("spotify_user_id")
    lyrics = data.get("lyrics", "")
    if not sid:
        return {"error": "missing_param", "message": "spotify_user_id is required"}, 400
    if not lyrics.strip():
        return {"error": "missing_param", "message": "lyrics is required"}, 400

    acct, db = _get_acct_and_db(sid)
    if not acct:
        return {"error": "not_linked"}, 404

    try:
        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
        overrides = data.get("overrides", {})
        overrides["lyrics"] = lyrics
        params = taste_to_caption(ut, overrides=overrides)

        if not acestep.health_check():
            return {"error": "acestep_unavailable"}, 503

        task_id = acestep.submit_task(params)

        gen = Generation(
            spotify_user_id=sid,
            task_id=task_id,
            status="pending",
            feature_type="lyric_mode",
            caption_used=params.get("prompt"),
            lyrics_used=lyrics,
            params_json=params,
        )
        db.add(gen)
        db.commit()
        db.refresh(gen)

        return {
            "generation_id": gen.id,
            "task_id": task_id,
            "status": "pending",
            "caption": params.get("prompt"),
        }
    except Exception as e:
        log.exception("lyric-mode failed")
        return {"error": "generation_failed", "detail": str(e)}, 500
    finally:
        db.close()


# ---------------------------------------------------------------
# GET /api/generate/status/<generation_id>
# ---------------------------------------------------------------
@generate_bp.get("/api/generate/status/<int:generation_id>")
def generation_status(generation_id: int):
    db = SessionLocal()
    try:
        gen = db.query(Generation).filter_by(id=generation_id).one_or_none()
        if not gen:
            return {"error": "not_found"}, 404

        # If already completed/failed, return cached status
        if gen.status in ("completed", "failed"):
            return _generation_response(gen)

        # Poll ACE-Step
        try:
            result = acestep.query_result(gen.task_id)
        except Exception as e:
            log.warning("Failed to poll ACE-Step: %s", e)
            return _generation_response(gen)

        status_code = result.get("status", 0)

        if status_code == 1:  # completed
            gen.status = "completed"
            gen.completed_at = datetime.now(timezone.utc)

            # Parse result to get audio path
            # ACE-Step returns result as a JSON string containing an array of
            # objects like: [{"file": "/path/to/audio.flac", "url": "...", ...}]
            result_data = result.get("result", "")
            if isinstance(result_data, str):
                try:
                    result_data = json.loads(result_data)
                except (json.JSONDecodeError, TypeError):
                    log.warning("Could not parse ACE-Step result: %s", result_data[:200] if result_data else "")
                    result_data = []

            # Extract audio file path from result
            audio_file_path = ""
            if isinstance(result_data, list) and result_data:
                first = result_data[0]
                if isinstance(first, dict):
                    audio_file_path = first.get("file", "")
                elif isinstance(first, str):
                    audio_file_path = first
            elif isinstance(result_data, dict):
                audio_file_path = result_data.get("file", "")

            if audio_file_path:
                try:
                    # Determine extension from the source file
                    ext = os.path.splitext(audio_file_path)[1] or ".wav"
                    audio_bytes = acestep.download_audio(audio_file_path)
                    local_path = os.path.join(
                        settings.audio_output_dir, f"{gen.id}{ext}"
                    )
                    os.makedirs(settings.audio_output_dir, exist_ok=True)
                    with open(local_path, "wb") as fp:
                        fp.write(audio_bytes)
                    gen.audio_path = local_path
                    log.info("Saved audio: %s (%d bytes)", local_path, len(audio_bytes))
                except Exception as e:
                    log.warning("Failed to save audio: %s", e)

            db.add(gen)
            db.commit()
            db.refresh(gen)

        elif status_code == 2:  # failed
            gen.status = "failed"
            db.add(gen)
            db.commit()

        return _generation_response(gen)
    finally:
        db.close()


def _generation_response(gen: Generation) -> Dict[str, Any]:
    return {
        "generation_id": gen.id,
        "task_id": gen.task_id,
        "status": gen.status,
        "feature_type": gen.feature_type,
        "caption": gen.caption_used,
        "lyrics": gen.lyrics_used,
        "params": gen.params_json,
        "audio_url": f"/api/audio/{gen.id}" if gen.audio_path else None,
        "duration_seconds": gen.duration_seconds,
        "title": gen.title,
        "is_favorite": gen.is_favorite,
        "created_at": gen.created_at.isoformat() if gen.created_at else None,
        "completed_at": gen.completed_at.isoformat() if gen.completed_at else None,
    }


# ---------------------------------------------------------------
# GET /api/audio/<generation_id>
# ---------------------------------------------------------------
@generate_bp.get("/api/audio/<int:generation_id>")
def serve_audio(generation_id: int):
    db = SessionLocal()
    try:
        gen = db.query(Generation).filter_by(id=generation_id).one_or_none()
        if not gen or not gen.audio_path:
            return {"error": "not_found"}, 404
        if not os.path.isfile(gen.audio_path):
            return {"error": "audio_file_missing"}, 404
        ext = os.path.splitext(gen.audio_path)[1].lower()
        mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg"}.get(ext, "audio/wav")
        return send_file(gen.audio_path, mimetype=mime)
    finally:
        db.close()


# ---------------------------------------------------------------
# GET /api/generate/history
# ---------------------------------------------------------------
@generate_bp.get("/api/generate/history")
def generation_history():
    sid = request.args.get("spotify_user_id")
    if not sid:
        return {"error": "missing_param"}, 400

    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except (ValueError, TypeError):
        limit = 50
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0

    db = SessionLocal()
    try:
        gens = (
            db.query(Generation)
            .filter_by(spotify_user_id=sid)
            .order_by(Generation.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "items": [_generation_response(g) for g in gens],
            "count": len(gens),
            "limit": limit,
            "offset": offset,
        }
    finally:
        db.close()


# ---------------------------------------------------------------
# POST /api/generate/<id>/favorite
# ---------------------------------------------------------------
@generate_bp.post("/api/generate/<int:generation_id>/favorite")
def toggle_favorite(generation_id: int):
    db = SessionLocal()
    try:
        gen = db.query(Generation).filter_by(id=generation_id).one_or_none()
        if not gen:
            return {"error": "not_found"}, 404
        gen.is_favorite = 0 if gen.is_favorite else 1
        db.add(gen)
        db.commit()
        return {"generation_id": gen.id, "is_favorite": gen.is_favorite}
    finally:
        db.close()


# ---------------------------------------------------------------
# PATCH /api/generate/<id>
# ---------------------------------------------------------------
@generate_bp.patch("/api/generate/<int:generation_id>")
def update_generation(generation_id: int):
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        gen = db.query(Generation).filter_by(id=generation_id).one_or_none()
        if not gen:
            return {"error": "not_found"}, 404
        if "title" in data:
            gen.title = data["title"]
        if "is_favorite" in data:
            gen.is_favorite = 1 if data["is_favorite"] else 0
        db.add(gen)
        db.commit()
        db.refresh(gen)
        return _generation_response(gen)
    finally:
        db.close()


# ---------------------------------------------------------------
# DELETE /api/generate/<id>
# ---------------------------------------------------------------
@generate_bp.delete("/api/generate/<int:generation_id>")
def delete_generation(generation_id: int):
    db = SessionLocal()
    try:
        gen = db.query(Generation).filter_by(id=generation_id).one_or_none()
        if not gen:
            return {"error": "not_found"}, 404
        # Remove audio file if exists
        if gen.audio_path and os.path.isfile(gen.audio_path):
            os.remove(gen.audio_path)
        db.delete(gen)
        db.commit()
        return {"ok": True, "deleted": generation_id}
    finally:
        db.close()


# ---------------------------------------------------------------
# GET /api/acestep/health
# ---------------------------------------------------------------
@generate_bp.get("/api/acestep/health")
def acestep_health():
    healthy = acestep.health_check()
    return {"ok": healthy}

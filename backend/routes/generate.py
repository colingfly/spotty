# backend/routes/generate.py
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, g, request, send_file

from config import settings
from db import SessionLocal
from extensions import limiter
from models import Generation, SpotifyAccount, UserTaste
from services.acestep_client import acestep
from services.auth_tokens import require_user, verify_audio
from services.caption_engine import MODE_TO_FEATURE_TYPE, MODES, PRESETS, ComposeRequest, ComposeResult, compose, preset_catalog
from services.generation_service import serialize, submit_batch, sync_generation
from services.spotify_client import artist_genres_with_fallback, get_artists, refresh_if_needed
from services.taste import update_user_taste_if_stale

log = logging.getLogger("spotty.generate")

generate_bp = Blueprint("generate", __name__)

_FEATURE_TYPE_TO_MODE = {v: k for k, v in MODE_TO_FEATURE_TYPE.items()}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _load_user(db) -> Tuple[Optional[SpotifyAccount], Optional[UserTaste], Optional[Tuple[dict, int]]]:
    acct = db.query(SpotifyAccount).filter_by(spotify_user_id=g.sid).one_or_none()
    if not acct:
        return None, None, ({"error": "not_linked"}, 404)
    try:
        acct = refresh_if_needed(acct, db)
    except Exception as e:
        return None, None, ({"error": "reauth_required", "message": str(e)}, 401)
    try:
        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)
    except Exception as e:
        log.exception("taste build failed")
        return None, None, ({"error": "taste_unavailable", "message": str(e)}, 502)
    return acct, ut, None


def _own_generation(db, generation_id: int) -> Optional[Generation]:
    return db.query(Generation).filter_by(id=generation_id, spotify_user_id=g.sid).one_or_none()


def _resolve_fusion_artists(acct: SpotifyAccount, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Accept artist ids (from top artists) and/or free names (from a poster scan)."""
    out: List[Dict[str, Any]] = []
    ids = [str(i) for i in (data.get("artist_ids") or []) if i][:8]
    if ids:
        for a in get_artists(acct, ids):
            out.append({"name": a["name"], "genres": artist_genres_with_fallback(a)[:6], "image": a.get("image")})
    for name in (data.get("artist_names") or [])[:10]:
        name = str(name).strip()
        if name and not any(o["name"].lower() == name.lower() for o in out):
            out.append({"name": name, "genres": artist_genres_with_fallback({"name": name})[:6]})
    return out


def _build_request(acct: SpotifyAccount, ut: UserTaste, data: Dict[str, Any]) -> ComposeRequest:
    mode = str(data.get("mode") or "taste").lower()
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")

    overrides = data.get("overrides") or {}
    if not isinstance(overrides, dict):
        overrides = {}

    lyrics = (data.get("lyrics") or "").strip() or None
    if lyrics and len(lyrics) > 4096:
        raise ValueError("lyrics must be 4096 characters or fewer")
    theme = (data.get("lyrics_theme") or "").strip()[:200] or None
    brief = (data.get("brief") or "").strip()[:600] or None
    if mode == "brief" and not brief:
        raise ValueError("brief mode needs a creative brief")
    if mode == "lyrics" and not (lyrics or theme):
        raise ValueError("lyrics mode needs lyrics or a theme")

    want_vocals = data.get("vocals")
    if want_vocals is None:
        want_vocals = mode == "lyrics" or (ut.instrumentalness or 0) < 0.5
    want_vocals = bool(want_vocals)
    if mode == "lyrics":
        want_vocals = True

    try:
        duration = int(data.get("duration") or settings.default_duration_seconds)
    except (TypeError, ValueError):
        duration = settings.default_duration_seconds

    fusion_artists: List[Dict[str, Any]] = []
    if mode in ("fusion", "festival"):
        fusion_artists = _resolve_fusion_artists(acct, data)
        if len(fusion_artists) < (2 if mode == "fusion" else 1):
            raise ValueError("fusion needs at least two artists; festival needs at least one")

    preset = data.get("preset") or None
    if preset and preset not in PRESETS:
        raise ValueError(f"unknown preset: {preset}")

    return ComposeRequest(
        mode=mode,
        features=ut.as_features(),
        genres=list(ut.genres or []),
        genre_weights=list(ut.genre_weights or []),
        top_artists=list(ut.top_artists or []),
        overrides=overrides,
        preset=preset,
        brief=brief,
        lyrics=lyrics,
        lyrics_theme=theme,
        want_vocals=want_vocals,
        fusion_artists=fusion_artists,
        duration=duration,
        use_llm=data.get("use_llm", True) is not False,
    )


_KEY_RE = re.compile(r"^[A-G][#b]? (major|minor)$")


def _apply_edits(result: ComposeResult, edits: Optional[Dict[str, Any]]) -> ComposeResult:
    """Let the user tweak the composed brief before it is submitted."""
    if not edits or not isinstance(edits, dict):
        return result
    if isinstance(edits.get("title"), str) and edits["title"].strip():
        result.title = edits["title"].strip()[:80]
    if isinstance(edits.get("prompt"), str) and edits["prompt"].strip():
        result.prompt = edits["prompt"].strip()[:1200]
    if isinstance(edits.get("lyrics"), str):
        result.lyrics = edits["lyrics"].strip()[:4096] or "[Instrumental]"
    if edits.get("bpm") is not None:
        try:
            result.bpm = int(max(40, min(220, int(edits["bpm"]))))
        except (TypeError, ValueError):
            pass
    if edits.get("key_scale") is not None:
        ks = str(edits["key_scale"]).strip()
        result.key_scale = ks if _KEY_RE.match(ks) else None
    if edits.get("duration") is not None:
        try:
            result.duration = int(max(15, min(settings.max_duration_seconds, int(edits["duration"]))))
        except (TypeError, ValueError):
            pass
    return result


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------

@generate_bp.get("/api/generate/presets")
def presets():
    return {"items": preset_catalog(), "modes": list(MODES)}


@generate_bp.get("/api/acestep/health")
def acestep_health():
    return {"ok": acestep.health_check()}


# --------------------------------------------------------------------------
# Compose (preview) and generate
# --------------------------------------------------------------------------

@generate_bp.post("/api/generate/preview")
@require_user
@limiter.limit(settings.rate_limit_llm)
def preview():
    """Compose the brief without submitting it, so the user can read and edit it first."""
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        acct, ut, err = _load_user(db)
        if err:
            return err
        try:
            req = _build_request(acct, ut, data)
        except ValueError as e:
            return {"error": "bad_request", "message": str(e)}, 400
        result = compose(req)
        return {"composed": result.to_dict(), "fusion_artists": req.fusion_artists}
    finally:
        db.close()


@generate_bp.post("/api/generate")
@require_user
@limiter.limit(settings.rate_limit_generate)
def generate():
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        acct, ut, err = _load_user(db)
        if err:
            return err
        try:
            req = _build_request(acct, ut, data)
        except ValueError as e:
            return {"error": "bad_request", "message": str(e)}, 400

        if not acestep.health_check():
            return {"error": "acestep_unavailable", "message": "The ACE-Step GPU server is offline."}, 503

        result = compose(req)
        result = _apply_edits(result, data.get("edits"))

        try:
            variations = int(data.get("variations") or 1)
        except (TypeError, ValueError):
            variations = 1

        meta = {
            "overrides": req.overrides,
            "brief": req.brief,
            "lyrics_theme": req.lyrics_theme,
            "fusion_artists": req.fusion_artists,
            "edited": bool(data.get("edits")),
        }
        try:
            rows = submit_batch(db, g.sid, result, variations=variations, meta=meta)
        except Exception as e:
            log.exception("ACE-Step submit failed")
            return {"error": "generation_failed", "message": str(e)[:300]}, 502

        return {
            "batch_id": rows[0].batch_id,
            "items": [serialize(r) for r in rows],
            "composed": result.to_dict(),
        }, 202
    finally:
        db.close()


# Legacy endpoints: map onto the unified flow so older clients keep working.
def _legacy(mode: str, feature_overrides: Optional[Dict[str, Any]] = None):
    data = request.get_json(silent=True) or {}
    data["mode"] = mode
    if feature_overrides:
        data.update(feature_overrides)
    request._cached_json = (data, data)  # type: ignore[attr-defined]
    return generate()


@generate_bp.post("/api/generate/taste-to-track")
@require_user
@limiter.limit(settings.rate_limit_generate)
def legacy_taste():
    return _legacy("taste")


@generate_bp.post("/api/generate/custom")
@require_user
@limiter.limit(settings.rate_limit_generate)
def legacy_custom():
    return _legacy("mood")


@generate_bp.post("/api/generate/lyric-mode")
@require_user
@limiter.limit(settings.rate_limit_generate)
def legacy_lyrics():
    return _legacy("lyrics")


# --------------------------------------------------------------------------
# Lyrics writer
# --------------------------------------------------------------------------

@generate_bp.post("/api/compose/lyrics")
@require_user
@limiter.limit(settings.rate_limit_llm)
def compose_lyrics():
    from services import llm

    data = request.get_json(silent=True) or {}
    theme = (data.get("theme") or "").strip()[:300]
    if not theme:
        return {"error": "bad_request", "message": "theme is required"}, 400
    if not llm.available():
        return {"error": "llm_unavailable", "message": "Set ANTHROPIC_API_KEY to enable the lyric writer."}, 503

    db = SessionLocal()
    try:
        acct, ut, err = _load_user(db)
        if err:
            return err
        payload = {
            "theme": theme,
            "mood": (data.get("mood") or "").strip()[:100] or None,
            "structure": (data.get("structure") or "verse-chorus-verse-chorus-bridge-chorus"),
            "features": {k: round(float(v), 3) for k, v in ut.as_features().items()},
            "genre_weights": (ut.genre_weights or [])[:10],
            "perspective": (data.get("perspective") or "first person"),
        }
        try:
            return llm.write_lyrics(payload)
        except Exception as e:
            log.warning("lyric writer failed: %s", e)
            return {"error": "llm_failed", "message": "Could not write lyrics right now."}, 502
    finally:
        db.close()


# --------------------------------------------------------------------------
# Status, library
# --------------------------------------------------------------------------

@generate_bp.get("/api/generate/status/<int:generation_id>")
@require_user
def generation_status(generation_id: int):
    db = SessionLocal()
    try:
        gen = _own_generation(db, generation_id)
        if not gen:
            return {"error": "not_found"}, 404
        gen = sync_generation(db, gen)
        return serialize(gen)
    finally:
        db.close()


@generate_bp.get("/api/generate/batch/<batch_id>")
@require_user
def batch_status(batch_id: str):
    db = SessionLocal()
    try:
        rows = (
            db.query(Generation)
            .filter_by(batch_id=batch_id, spotify_user_id=g.sid)
            .order_by(Generation.variation_index.asc())
            .all()
        )
        if not rows:
            return {"error": "not_found"}, 404
        rows = [sync_generation(db, r) for r in rows]
        done = all(r.status in ("completed", "failed") for r in rows)
        return {"batch_id": batch_id, "done": done, "items": [serialize(r) for r in rows]}
    finally:
        db.close()


@generate_bp.get("/api/generate/history")
@require_user
def generation_history():
    def _int(name, default, lo, hi):
        try:
            return min(max(int(request.args.get(name, default)), lo), hi)
        except (TypeError, ValueError):
            return default

    limit = _int("limit", 50, 1, 200)
    offset = _int("offset", 0, 0, 100000)
    only_fav = request.args.get("favorites") in ("1", "true")
    mode = request.args.get("mode")
    status = request.args.get("status")
    q_text = (request.args.get("q") or "").strip().lower()
    sort = request.args.get("sort", "newest")

    db = SessionLocal()
    try:
        q = db.query(Generation).filter(Generation.spotify_user_id == g.sid)
        if only_fav:
            q = q.filter(Generation.is_favorite == 1)
        if mode and mode in MODE_TO_FEATURE_TYPE:
            q = q.filter(Generation.feature_type == MODE_TO_FEATURE_TYPE[mode])
        if status in ("pending", "processing", "completed", "failed"):
            q = q.filter(Generation.status == status)
        if q_text:
            like = f"%{q_text}%"
            q = q.filter((Generation.title.ilike(like)) | (Generation.caption_used.ilike(like)) | (Generation.lyrics_used.ilike(like)))
        total = q.count()
        if sort == "oldest":
            q = q.order_by(Generation.created_at.asc())
        elif sort == "plays":
            q = q.order_by(Generation.play_count.desc(), Generation.created_at.desc())
        else:
            q = q.order_by(Generation.created_at.desc())
        gens = q.offset(offset).limit(limit).all()
        # Opportunistically sync anything still active so the library is never stale
        gens = [sync_generation(db, gnr) if gnr.status in ("pending", "processing") else gnr for gnr in gens]
        return {"items": [serialize(gnr) for gnr in gens], "count": len(gens), "total": total, "limit": limit, "offset": offset}
    finally:
        db.close()


@generate_bp.post("/api/generate/<int:generation_id>/favorite")
@require_user
def toggle_favorite(generation_id: int):
    db = SessionLocal()
    try:
        gen = _own_generation(db, generation_id)
        if not gen:
            return {"error": "not_found"}, 404
        gen.is_favorite = 0 if gen.is_favorite else 1
        db.commit()
        db.refresh(gen)
        return serialize(gen)
    finally:
        db.close()


@generate_bp.post("/api/generate/<int:generation_id>/played")
@require_user
def mark_played(generation_id: int):
    db = SessionLocal()
    try:
        gen = _own_generation(db, generation_id)
        if not gen:
            return {"error": "not_found"}, 404
        gen.play_count = (gen.play_count or 0) + 1
        db.commit()
        return {"generation_id": gen.id, "play_count": gen.play_count}
    finally:
        db.close()


@generate_bp.patch("/api/generate/<int:generation_id>")
@require_user
def update_generation(generation_id: int):
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        gen = _own_generation(db, generation_id)
        if not gen:
            return {"error": "not_found"}, 404
        if "title" in data:
            title = str(data["title"] or "").strip()[:80]
            gen.title = title or None
        if "is_favorite" in data:
            gen.is_favorite = 1 if data["is_favorite"] else 0
        db.commit()
        db.refresh(gen)
        return serialize(gen)
    finally:
        db.close()


@generate_bp.delete("/api/generate/<int:generation_id>")
@require_user
def delete_generation(generation_id: int):
    db = SessionLocal()
    try:
        gen = _own_generation(db, generation_id)
        if not gen:
            return {"error": "not_found"}, 404
        if gen.audio_path and os.path.isfile(gen.audio_path):
            try:
                os.remove(gen.audio_path)
            except OSError as e:
                log.warning("Could not remove %s: %s", gen.audio_path, e)
        db.delete(gen)
        db.commit()
        return {"ok": True, "deleted": generation_id}
    finally:
        db.close()


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------

_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.-]+")


@generate_bp.get("/api/audio/<int:generation_id>")
@limiter.exempt
def serve_audio(generation_id: int):
    token = request.args.get("t", "")
    if not token or not verify_audio(token, generation_id):
        return {"error": "unauthorized"}, 401
    db = SessionLocal()
    try:
        gen = db.query(Generation).filter_by(id=generation_id).one_or_none()
        if not gen or not gen.audio_path:
            return {"error": "not_found"}, 404
        if not os.path.isfile(gen.audio_path):
            return {"error": "audio_file_missing"}, 404
        ext = os.path.splitext(gen.audio_path)[1].lower()
        mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg"}.get(ext, "audio/mpeg")
        as_attachment = request.args.get("download") in ("1", "true")
        name = _SAFE_NAME.sub("", gen.title or f"trill-{gen.id}").strip() or f"trill-{gen.id}"
        resp = send_file(
            gen.audio_path,
            mimetype=mime,
            as_attachment=as_attachment,
            download_name=f"{name}{ext}",
            conditional=True,
        )
        resp.headers["Cache-Control"] = "private, max-age=86400"
        return resp
    finally:
        db.close()

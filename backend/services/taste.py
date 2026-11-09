# backend/services/taste.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import SpotifyAccount, UserTaste
from services.spotify_client import collect_taste_inputs, user_audio_features_profile

log = logging.getLogger("spotty.taste")

NARRATIVE_MAX_AGE_HOURS = 24 * 7


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age_hours(dt: Optional[datetime]) -> float:
    dt = _utc(dt)
    if not dt:
        return float("inf")
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def rebuild_user_taste(acct: SpotifyAccount, db: Session) -> UserTaste:
    """Pull fresh data from Spotify + Last.fm and (re)write the UserTaste row."""
    weighted, names, _ = collect_taste_inputs(acct)
    if not weighted and not names:
        # Spotify returned nothing (expired token, outage). Never clobber a good profile with zeros.
        raise RuntimeError("Spotify returned no listening data; keeping the existing profile")
    audio = user_audio_features_profile(acct, weighted)
    genres = [w["genre"] for w in weighted]
    now = datetime.now(timezone.utc)

    ut = db.query(UserTaste).filter_by(spotify_user_id=acct.spotify_user_id).one_or_none()
    if not ut:
        ut = UserTaste(spotify_user_id=acct.spotify_user_id)
        db.add(ut)

    ut.updated_at = now
    ut.genres = genres
    ut.genre_weights = weighted[:40]
    ut.top_artists = names[:30]
    for k, v in audio.items():
        setattr(ut, k, float(v))
    # A new profile invalidates the cached narrative
    ut.narrative_json = None
    ut.narrative_updated_at = None

    db.commit()
    db.refresh(ut)
    log.info("Rebuilt taste for %s: %d genres, %d artists", acct.spotify_user_id, len(genres), len(names))
    return ut


def get_user_taste(acct: SpotifyAccount, db: Session) -> UserTaste:
    ut = db.query(UserTaste).filter_by(spotify_user_id=acct.spotify_user_id).one_or_none()
    return ut or rebuild_user_taste(acct, db)


def update_user_taste_if_stale(acct: SpotifyAccount, db: Session, max_age_hours: int = 24) -> UserTaste:
    ut = db.query(UserTaste).filter_by(spotify_user_id=acct.spotify_user_id).one_or_none()
    if ut and _age_hours(ut.updated_at) < max_age_hours and ut.genre_weights is not None:
        return ut
    try:
        return rebuild_user_taste(acct, db)
    except Exception as e:
        if ut is not None:
            log.warning("Taste rebuild failed for %s (%s); serving cached profile", acct.spotify_user_id, e)
            db.rollback()
            return ut
        raise


def taste_payload(ut: UserTaste) -> Dict[str, Any]:
    return {
        "spotify_user_id": ut.spotify_user_id,
        **{k: round(float(v), 4) for k, v in ut.as_features().items()},
        "genres": ut.genres or [],
        "genre_weights": ut.genre_weights or [],
        "top_artists": ut.top_artists or [],
        "updated_at": _utc(ut.updated_at).isoformat() if ut.updated_at else None,
        "narrative": ut.narrative_json,
    }


def get_or_build_narrative(ut: UserTaste, db: Session, force: bool = False) -> Optional[Dict[str, Any]]:
    """Claude-written Sound DNA card, cached on the taste row. None if the LLM is unavailable."""
    if not force and ut.narrative_json and _age_hours(ut.narrative_updated_at) < NARRATIVE_MAX_AGE_HOURS:
        return ut.narrative_json
    try:
        from services import llm

        if not llm.available():
            return ut.narrative_json
        payload = {
            "features": {k: round(float(v), 3) for k, v in ut.as_features().items()},
            "genre_weights": (ut.genre_weights or [])[:20],
            "top_artists": (ut.top_artists or [])[:20],
        }
        narrative = llm.sound_dna(payload)
        ut.narrative_json = narrative
        ut.narrative_updated_at = datetime.now(timezone.utc)
        db.commit()
        return narrative
    except Exception as e:
        log.warning("Narrative generation failed: %s", e)
        return ut.narrative_json

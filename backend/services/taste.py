# backend/services/taste.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import SpotifyAccount, UserTaste
from services.spotify_client import user_top_genres, user_audio_features_profile


def get_user_taste(acct: SpotifyAccount, db: Session) -> UserTaste:
    ut = (
        db.query(UserTaste)
        .filter_by(spotify_user_id=acct.spotify_user_id)
        .one_or_none()
    )
    if ut:
        return ut

    genres = user_top_genres(acct)
    audio = user_audio_features_profile(acct)
    ut = UserTaste(
        spotify_user_id=acct.spotify_user_id,
        updated_at=datetime.now(timezone.utc),
        danceability=audio["danceability"],
        energy=audio["energy"],
        valence=audio["valence"],
        acousticness=audio["acousticness"],
        instrumentalness=audio["instrumentalness"],
        liveness=audio["liveness"],
        speechiness=audio["speechiness"],
        tempo=audio["tempo"],
        genres=genres,
    )
    db.add(ut)
    db.commit()
    db.refresh(ut)
    return ut


def update_user_taste_if_stale(
    acct: SpotifyAccount, db: Session, max_age_hours: int = 24
) -> UserTaste:
    ut = (
        db.query(UserTaste)
        .filter_by(spotify_user_id=acct.spotify_user_id)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if (
        ut
        and ut.updated_at
        and (now - ut.updated_at.replace(tzinfo=timezone.utc)).total_seconds() < max_age_hours * 3600
    ):
        return ut

    genres = user_top_genres(acct)
    audio = user_audio_features_profile(acct)
    if ut:
        ut.updated_at = now
        ut.genres = genres
        ut.danceability = audio["danceability"]
        ut.energy = audio["energy"]
        ut.valence = audio["valence"]
        ut.acousticness = audio["acousticness"]
        ut.instrumentalness = audio["instrumentalness"]
        ut.liveness = audio["liveness"]
        ut.speechiness = audio["speechiness"]
        ut.tempo = audio["tempo"]
        db.add(ut)
    else:
        ut = UserTaste(
            spotify_user_id=acct.spotify_user_id,
            updated_at=now,
            genres=genres,
            **audio,
        )
        db.add(ut)
    db.commit()
    db.refresh(ut)
    return ut

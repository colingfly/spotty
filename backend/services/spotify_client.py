# backend/services/spotify_client.py
from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy.orm import Session

from config import settings
from models import SpotifyAccount

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


def spotify_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.timeout = 15
    return s


def basic_auth_header() -> Dict[str, str]:
    raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def refresh_if_needed(acct: SpotifyAccount, db: Session) -> SpotifyAccount:
    if time.time() < (acct.expires_at - 30):
        return acct
    if not acct.refresh_token:
        raise RuntimeError("Missing refresh token; user must re-auth.")

    sess = spotify_session()
    r = sess.post(
        TOKEN_URL,
        headers=basic_auth_header(),
        data={
            "grant_type": "refresh_token",
            "refresh_token": acct.refresh_token,
            "redirect_uri": settings.spotify_redirect_uri,
        },
    )
    if r.status_code != 200:
        raise RuntimeError(f"Refresh failed: {r.status_code} {r.text}")

    payload = r.json()
    acct.access_token = payload["access_token"]
    acct.expires_at = int(time.time()) + int(payload.get("expires_in", 3600))
    if "refresh_token" in payload:
        acct.refresh_token = payload["refresh_token"]
    acct.scope = payload.get("scope", acct.scope)
    acct.token_type = payload.get("token_type", acct.token_type)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def search_artist(name: str, bearer: str) -> Optional[Dict[str, Any]]:
    sess = spotify_session()
    r = sess.get(
        f"{API_BASE}/search",
        headers={"Authorization": f"Bearer {bearer}"},
        params={"q": name, "type": "artist", "limit": 3},
    )
    if r.status_code != 200:
        return None
    items = (r.json().get("artists") or {}).get("items") or []
    return items[0] if items else None


def user_top_artists(
    acct: SpotifyAccount, time_range: str = "long_term", limit: int = 50
) -> List[Dict[str, Any]]:
    sess = spotify_session()
    r = sess.get(
        f"{API_BASE}/me/top/artists",
        headers={"Authorization": f"Bearer {acct.access_token}"},
        params={"time_range": time_range, "limit": limit},
    )
    if r.status_code != 200:
        return []
    return r.json().get("items", [])


def user_top_genres(acct: SpotifyAccount) -> List[str]:
    from services.artist_genre_map import get_artist_genres

    artists = user_top_artists(acct, time_range="long_term", limit=50)
    seen: set = set()
    out: List[str] = []
    for a in artists:
        genres = a.get("genres", [])
        if not genres:
            genres = get_artist_genres(a.get("name", ""))
        for g in genres:
            gl = g.lower()
            if gl not in seen:
                seen.add(gl)
                out.append(gl)
    return out


def user_audio_features_profile(acct: SpotifyAccount) -> Dict[str, float]:
    """
    Compute audio features for a user's taste profile.

    Strategy:
    1. Try librosa analysis on preview clips (most accurate)
    2. Fall back to genre-based inference (always available)
    """
    import logging
    from services.audio_analyzer import analyze_tracks
    from services.genre_analyzer import infer_audio_features

    log = logging.getLogger("spotty")
    sess = spotify_session()

    # Get top tracks
    r1 = sess.get(
        f"{API_BASE}/me/top/tracks",
        headers={"Authorization": f"Bearer {acct.access_token}"},
        params={"time_range": "medium_term", "limit": 50, "market": "US"},
    )
    tracks = r1.json().get("items", []) if r1.status_code == 200 else []

    # Try preview URL analysis first
    preview_urls = [t["preview_url"] for t in tracks if t.get("preview_url")]
    log.info(f"Found {len(preview_urls)}/{len(tracks)} tracks with preview URLs")

    if preview_urls:
        return analyze_tracks(preview_urls)

    # Fallback: genre-based inference from top artists
    log.info("No preview URLs — using genre-based inference")
    from services.artist_genre_map import get_artist_genres

    artists = user_top_artists(acct, "long_term", limit=50)
    all_genres: List[str] = []
    weights: List[float] = []
    for i, a in enumerate(artists):
        # Try Spotify genres first, then our own mapper
        genres = a.get("genres", [])
        if not genres:
            genres = get_artist_genres(a.get("name", ""))
        for g in genres:
            all_genres.append(g)
            weights.append(1.0 / (1.0 + 0.2 * i))

    log.info(f"Collected {len(all_genres)} genre tags from {len(artists)} artists")
    return infer_audio_features(all_genres, weights)


def artist_audio_features(acct: SpotifyAccount, artist_id: str) -> Dict[str, float]:
    """Get audio features for an artist (preview clips or genre fallback)."""
    from services.audio_analyzer import analyze_tracks
    from services.genre_analyzer import infer_audio_features

    sess = spotify_session()
    r = sess.get(
        f"{API_BASE}/artists/{artist_id}/top-tracks",
        headers={"Authorization": f"Bearer {acct.access_token}"},
        params={"market": "US"},
    )
    keys = [
        "danceability", "energy", "valence",
        "acousticness", "instrumentalness", "liveness",
        "speechiness", "tempo",
    ]
    if r.status_code != 200:
        return {k: 0.0 for k in keys}

    tracks = r.json().get("tracks", [])
    preview_urls = [t["preview_url"] for t in tracks if t.get("preview_url")]
    if preview_urls:
        return analyze_tracks(preview_urls)

    # Fallback: genre-based
    genres = artist_genres(acct, artist_id)
    if genres:
        return infer_audio_features(genres)
    return {k: 0.0 for k in keys}


def artist_genres(acct: SpotifyAccount, artist_id: str) -> List[str]:
    """Get genres for a specific artist."""
    from services.artist_genre_map import get_artist_genres

    sess = spotify_session()
    r = sess.get(
        f"{API_BASE}/artists/{artist_id}",
        headers={"Authorization": f"Bearer {acct.access_token}"},
    )
    if r.status_code != 200:
        return []
    data = r.json()
    genres = [g.lower() for g in data.get("genres", [])]
    if not genres:
        genres = get_artist_genres(data.get("name", ""))
    return genres

# backend/services/spotify_client.py
from __future__ import annotations

import base64
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from config import settings
from models import SpotifyAccount

log = logging.getLogger("spotty.spotify")

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

TIME_RANGES = ("short_term", "medium_term", "long_term")


class SpotifyError(RuntimeError):
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"Spotify API {status}: {body[:200]}")
        self.status = status
        self.body = body


def spotify_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def basic_auth_header() -> Dict[str, str]:
    raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def _bearer(acct: SpotifyAccount) -> Dict[str, str]:
    return {"Authorization": f"Bearer {acct.access_token}"}


def _get(acct: SpotifyAccount, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = spotify_session().get(f"{API_BASE}{path}", headers=_bearer(acct), params=params or {}, timeout=15)
    if r.status_code != 200:
        raise SpotifyError(r.status_code, r.text)
    return r.json() or {}


# --- tokens ---------------------------------------------------------------

def refresh_if_needed(acct: SpotifyAccount, db: Session) -> SpotifyAccount:
    if time.time() < (acct.expires_at - 60):
        return acct
    if not acct.refresh_token:
        raise RuntimeError("Missing refresh token; user must re-auth.")

    r = spotify_session().post(
        TOKEN_URL,
        headers=basic_auth_header(),
        data={"grant_type": "refresh_token", "refresh_token": acct.refresh_token},
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Refresh failed: {r.status_code} {r.text[:200]}")

    payload = r.json()
    acct.access_token = payload["access_token"]
    acct.expires_at = int(time.time()) + int(payload.get("expires_in", 3600))
    if payload.get("refresh_token"):
        acct.refresh_token = payload["refresh_token"]
    acct.scope = payload.get("scope", acct.scope)
    acct.token_type = payload.get("token_type", acct.token_type)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


# --- profile --------------------------------------------------------------

def fetch_me(acct: SpotifyAccount) -> Dict[str, Any]:
    me = _get(acct, "/me")
    images = me.get("images") or []
    return {
        "id": me.get("id"),
        "display_name": me.get("display_name") or me.get("id"),
        "avatar_url": (images[0].get("url") if images else None),
        "country": me.get("country"),
        "product": me.get("product"),
        "external_url": (me.get("external_urls") or {}).get("spotify"),
    }


# --- library --------------------------------------------------------------

def _shape_artist(a: Dict[str, Any]) -> Dict[str, Any]:
    images = a.get("images") or []
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "genres": [g.lower() for g in a.get("genres", [])],
        "popularity": a.get("popularity"),
        "image": images[0].get("url") if images else None,
        "external_url": (a.get("external_urls") or {}).get("spotify"),
        "followers": (a.get("followers") or {}).get("total"),
    }


def _shape_track(t: Dict[str, Any]) -> Dict[str, Any]:
    album = t.get("album") or {}
    images = album.get("images") or []
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "artists": [a.get("name") for a in t.get("artists", []) if a.get("name")],
        "album": album.get("name"),
        "image": images[0].get("url") if images else None,
        "external_url": (t.get("external_urls") or {}).get("spotify"),
        "popularity": t.get("popularity"),
        "duration_ms": t.get("duration_ms"),
        "explicit": t.get("explicit"),
    }


def user_top_artists_raw(acct: SpotifyAccount, time_range: str = "long_term", limit: int = 50) -> List[Dict[str, Any]]:
    try:
        return _get(acct, "/me/top/artists", {"time_range": time_range, "limit": limit}).get("items", [])
    except SpotifyError as e:
        log.warning("top artists failed: %s", e)
        return []


def user_top_artists(acct: SpotifyAccount, time_range: str = "long_term", limit: int = 50) -> List[Dict[str, Any]]:
    return [_shape_artist(a) for a in user_top_artists_raw(acct, time_range, limit)]


def user_top_tracks(acct: SpotifyAccount, time_range: str = "medium_term", limit: int = 20) -> List[Dict[str, Any]]:
    try:
        items = _get(acct, "/me/top/tracks", {"time_range": time_range, "limit": limit}).get("items", [])
    except SpotifyError as e:
        log.warning("top tracks failed: %s", e)
        return []
    return [_shape_track(t) for t in items]


def search_artist(name: str, acct: SpotifyAccount) -> Optional[Dict[str, Any]]:
    try:
        items = (_get(acct, "/search", {"q": name, "type": "artist", "limit": 3}).get("artists") or {}).get("items") or []
    except SpotifyError:
        return None
    return items[0] if items else None


def get_artists(acct: SpotifyAccount, ids: List[str]) -> List[Dict[str, Any]]:
    ids = [i for i in ids if i][:50]
    if not ids:
        return []
    try:
        return [_shape_artist(a) for a in _get(acct, "/artists", {"ids": ",".join(ids)}).get("artists", []) if a]
    except SpotifyError as e:
        log.warning("get artists failed: %s", e)
        return []


def artist_genres_with_fallback(artist: Dict[str, Any]) -> List[str]:
    """Spotify stopped returning genres for most artists in 2024; use Last.fm when empty."""
    from services.artist_genre_map import get_artist_genres

    genres = [g.lower() for g in artist.get("genres") or []]
    if not genres and artist.get("name"):
        genres = get_artist_genres(artist["name"])
    return genres


# --- taste inputs ---------------------------------------------------------

def collect_taste_inputs(acct: SpotifyAccount) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """
    Returns (weighted_genres, top_artist_names, artists_with_genres).

    weighted_genres: [{"genre": str, "weight": float}] sorted by weight.
    Weighting combines artist rank (earlier = heavier) and recency (artists
    appearing in the short-term list get a boost).
    """
    long_term = user_top_artists_raw(acct, "long_term", 50)
    short_term = user_top_artists_raw(acct, "short_term", 30)
    recent_ids = {a.get("id") for a in short_term}

    weights: Dict[str, float] = {}
    names: List[str] = []
    enriched: List[Dict[str, Any]] = []
    for i, a in enumerate(long_term):
        rank_w = 1.0 / (1.0 + 0.12 * i)
        recency = 1.35 if a.get("id") in recent_ids else 1.0
        genres = artist_genres_with_fallback(a)
        if a.get("name"):
            names.append(a["name"])
        enriched.append({"name": a.get("name"), "genres": genres})
        for j, g in enumerate(genres):
            g_w = rank_w * recency / (1.0 + 0.5 * j)
            weights[g] = weights.get(g, 0.0) + g_w

    # Artists only in the short-term list still count, lightly
    long_ids = {a.get("id") for a in long_term}
    for i, a in enumerate(short_term):
        if a.get("id") in long_ids:
            continue
        genres = artist_genres_with_fallback(a)
        if a.get("name"):
            names.append(a["name"])
        enriched.append({"name": a.get("name"), "genres": genres})
        for j, g in enumerate(genres):
            weights[g] = weights.get(g, 0.0) + 0.6 / (1.0 + 0.12 * i) / (1.0 + 0.5 * j)

    total = sum(weights.values()) or 1.0
    weighted = sorted(
        ({"genre": g, "weight": round(w / total, 4)} for g, w in weights.items()),
        key=lambda x: x["weight"],
        reverse=True,
    )
    return weighted, names, enriched


def user_audio_features_profile(acct: SpotifyAccount, weighted_genres: Optional[List[Dict[str, Any]]] = None) -> Dict[str, float]:
    """Infer the 8 audio features from weighted genre tags (Spotify audio-features API is gone)."""
    from services.genre_analyzer import infer_audio_features

    if weighted_genres is None:
        weighted_genres, _, _ = collect_taste_inputs(acct)
    genres = [w["genre"] for w in weighted_genres]
    weights = [float(w["weight"]) for w in weighted_genres]
    return infer_audio_features(genres, weights)

# backend/services/artist_genre_map.py
"""
Map artist names to genre tags using Last.fm's API.
Results are cached in-memory for the life of the process.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, List

import requests

from config import settings

log = logging.getLogger("spotty.lastfm")

_cache: Dict[str, List[str]] = {}
_lock = threading.Lock()

_SKIP_TAGS = frozenset({
    "seen live", "favorites", "favourites", "favourite", "favorite", "love", "awesome", "cool",
    "amazing", "beautiful", "best", "epic", "genius", "legend", "all", "spotify",
    "male vocalists", "female vocalists", "under 2000 listeners", "american", "british",
    "canadian", "australian", "usa", "uk", "00s", "10s", "90s", "80s", "70s", "60s",
})


def _lastfm_genres(artist_name: str) -> List[str]:
    if not settings.lastfm_api_key:
        return []
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "artist.getTopTags",
                "artist": artist_name,
                "autocorrect": 1,
                "api_key": settings.lastfm_api_key,
                "format": "json",
            },
            timeout=5,
        )
        if r.status_code != 200:
            return []
        tags = r.json().get("toptags", {}).get("tag", [])
        out: List[str] = []
        for t in tags[:10]:
            name = str(t.get("name", "")).lower().strip()
            try:
                count = int(t.get("count", 0))
            except (TypeError, ValueError):
                count = 0
            if name and name not in _SKIP_TAGS and count > 10:
                out.append(name)
        return out[:8]
    except Exception as e:
        log.warning("Last.fm lookup failed for '%s': %s", artist_name, e)
        return []


def get_artist_genres(artist_name: str) -> List[str]:
    key = (artist_name or "").lower().strip()
    if not key:
        return []
    with _lock:
        if key in _cache:
            return _cache[key]
    genres = _lastfm_genres(artist_name)
    with _lock:
        _cache[key] = genres
    if not genres:
        log.debug("No genres found for '%s'", artist_name)
    return genres

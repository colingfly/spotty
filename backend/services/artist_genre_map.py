# backend/services/artist_genre_map.py
"""
Map artist names to genre tags using Last.fm's free API.
Caches results in-memory to avoid redundant calls.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import requests

log = logging.getLogger("spotty")

# Last.fm public API key (free tier, no auth required)
LASTFM_API_KEY = "b25b959554ed76058ac220b7b2e0a026"

# In-memory cache: artist_name_lower -> genre list
_cache: Dict[str, List[str]] = {}

# Tags to filter out (meta tags, not actual genres)
_SKIP_TAGS = frozenset({
    "seen live", "favorites", "favourite", "love", "awesome", "cool",
    "amazing", "beautiful", "best", "epic", "genius", "legend",
    "male vocalists", "female vocalists", "under 2000 listeners",
})


def _lastfm_genres(artist_name: str) -> List[str]:
    """Fetch genre tags from Last.fm."""
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "artist.getTopTags",
                "artist": artist_name,
                "api_key": LASTFM_API_KEY,
                "format": "json",
            },
            timeout=5,
        )
        if r.status_code != 200:
            return []
        tags = r.json().get("toptags", {}).get("tag", [])
        return [
            t["name"].lower()
            for t in tags[:8]
            if t.get("name", "").lower() not in _SKIP_TAGS
            and int(t.get("count", 0)) > 10
        ]
    except Exception as e:
        log.warning(f"Last.fm lookup failed for '{artist_name}': {e}")
        return []


def get_artist_genres(artist_name: str) -> List[str]:
    """
    Get genre tags for an artist via Last.fm (cached).
    Scales to any artist — no hardcoded mappings needed.
    """
    key = artist_name.lower().strip()
    if key in _cache:
        return _cache[key]

    genres = _lastfm_genres(artist_name)
    _cache[key] = genres

    if genres:
        log.info(f"Genres for '{artist_name}': {genres}")
    else:
        log.warning(f"No genres found for '{artist_name}'")

    return genres

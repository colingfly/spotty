# backend/services/genre_analyzer.py
"""
Infer audio features from Spotify genre tags.
Uses a curated mapping of genre characteristics based on musicological research.
Falls back gracefully for unknown genres using keyword matching.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

log = logging.getLogger("spotty")

# Each genre maps to (danceability, energy, valence, acousticness,
#                      instrumentalness, liveness, speechiness, tempo_bpm)
# Values 0.0-1.0 except tempo which is BPM.
# Based on aggregated Spotify audio-features data pre-deprecation + musicological analysis.

GENRE_PROFILES: Dict[str, Tuple[float, ...]] = {
    # --- Hip-Hop / Rap ---
    "rap": (0.72, 0.65, 0.45, 0.10, 0.02, 0.15, 0.28, 130),
    "hip hop": (0.75, 0.63, 0.47, 0.10, 0.02, 0.14, 0.25, 128),
    "trap": (0.68, 0.62, 0.38, 0.08, 0.03, 0.12, 0.22, 140),
    "plugg": (0.65, 0.50, 0.35, 0.12, 0.05, 0.10, 0.18, 145),
    "pluggnb": (0.67, 0.48, 0.40, 0.14, 0.04, 0.10, 0.15, 140),
    "drill": (0.62, 0.68, 0.30, 0.06, 0.02, 0.13, 0.30, 142),
    "uk drill": (0.60, 0.70, 0.28, 0.05, 0.02, 0.14, 0.32, 140),
    "chicago drill": (0.60, 0.72, 0.25, 0.05, 0.02, 0.15, 0.30, 140),
    "mumble rap": (0.70, 0.58, 0.42, 0.10, 0.03, 0.12, 0.20, 135),
    "melodic rap": (0.68, 0.55, 0.45, 0.12, 0.03, 0.11, 0.18, 132),
    "conscious hip hop": (0.65, 0.55, 0.48, 0.15, 0.02, 0.18, 0.35, 95),
    "gangster rap": (0.70, 0.70, 0.35, 0.08, 0.02, 0.16, 0.30, 100),
    "southern hip hop": (0.74, 0.65, 0.50, 0.10, 0.02, 0.15, 0.22, 128),
    "dirty south rap": (0.75, 0.68, 0.48, 0.08, 0.02, 0.14, 0.20, 130),
    "crunk": (0.78, 0.80, 0.55, 0.05, 0.02, 0.20, 0.18, 130),
    "boom bap": (0.72, 0.58, 0.50, 0.12, 0.03, 0.15, 0.28, 92),
    "east coast hip hop": (0.70, 0.60, 0.48, 0.12, 0.02, 0.16, 0.30, 95),
    "west coast rap": (0.73, 0.62, 0.52, 0.10, 0.03, 0.14, 0.22, 100),
    "underground hip hop": (0.65, 0.58, 0.42, 0.15, 0.03, 0.18, 0.32, 95),
    "cloud rap": (0.60, 0.45, 0.38, 0.18, 0.08, 0.08, 0.15, 130),
    "emo rap": (0.55, 0.55, 0.25, 0.15, 0.05, 0.12, 0.18, 135),
    "rage rap": (0.62, 0.78, 0.30, 0.05, 0.02, 0.15, 0.22, 150),
    "florida rap": (0.72, 0.68, 0.48, 0.08, 0.02, 0.14, 0.22, 135),
    "detroit rap": (0.68, 0.72, 0.35, 0.06, 0.02, 0.15, 0.28, 138),
    "memphis rap": (0.70, 0.65, 0.38, 0.08, 0.03, 0.14, 0.24, 130),
    "atlanta rap": (0.73, 0.65, 0.48, 0.08, 0.02, 0.14, 0.22, 135),
    "houston rap": (0.72, 0.60, 0.45, 0.10, 0.03, 0.13, 0.20, 80),

    # --- R&B / Soul ---
    "r&b": (0.68, 0.50, 0.52, 0.25, 0.03, 0.12, 0.10, 110),
    "rnb": (0.68, 0.50, 0.52, 0.25, 0.03, 0.12, 0.10, 110),
    "neo soul": (0.62, 0.42, 0.55, 0.35, 0.05, 0.15, 0.08, 95),
    "soul": (0.65, 0.50, 0.60, 0.35, 0.04, 0.18, 0.08, 110),
    "contemporary r&b": (0.70, 0.52, 0.50, 0.20, 0.03, 0.12, 0.10, 115),
    "alternative r&b": (0.58, 0.45, 0.40, 0.28, 0.08, 0.10, 0.08, 105),
    "urban contemporary": (0.72, 0.55, 0.52, 0.18, 0.03, 0.12, 0.12, 118),

    # --- Pop ---
    "pop": (0.72, 0.65, 0.60, 0.18, 0.02, 0.12, 0.08, 120),
    "pop rap": (0.72, 0.65, 0.55, 0.10, 0.02, 0.12, 0.18, 128),
    "dance pop": (0.80, 0.78, 0.68, 0.08, 0.03, 0.15, 0.06, 122),
    "electropop": (0.75, 0.75, 0.58, 0.05, 0.08, 0.12, 0.06, 125),
    "indie pop": (0.60, 0.55, 0.55, 0.30, 0.05, 0.14, 0.05, 118),
    "art pop": (0.55, 0.55, 0.45, 0.22, 0.10, 0.12, 0.06, 115),
    "k-pop": (0.78, 0.78, 0.65, 0.08, 0.03, 0.14, 0.08, 125),
    "synth-pop": (0.72, 0.65, 0.55, 0.05, 0.10, 0.10, 0.06, 120),
    "bedroom pop": (0.55, 0.38, 0.48, 0.40, 0.08, 0.08, 0.05, 110),
    "hyperpop": (0.65, 0.82, 0.50, 0.03, 0.05, 0.10, 0.12, 150),

    # --- Electronic / Dance ---
    "edm": (0.75, 0.85, 0.55, 0.03, 0.20, 0.12, 0.05, 128),
    "electronic": (0.68, 0.72, 0.48, 0.05, 0.25, 0.10, 0.05, 125),
    "house": (0.78, 0.72, 0.55, 0.05, 0.22, 0.12, 0.04, 124),
    "deep house": (0.75, 0.60, 0.52, 0.08, 0.28, 0.10, 0.04, 122),
    "techno": (0.72, 0.80, 0.35, 0.03, 0.40, 0.12, 0.04, 130),
    "dubstep": (0.55, 0.85, 0.30, 0.03, 0.15, 0.12, 0.06, 140),
    "drum and bass": (0.60, 0.88, 0.40, 0.03, 0.18, 0.14, 0.05, 174),
    "ambient": (0.25, 0.20, 0.35, 0.40, 0.70, 0.05, 0.03, 90),
    "lo-fi": (0.55, 0.35, 0.45, 0.45, 0.30, 0.08, 0.04, 85),
    "lofi beats": (0.58, 0.32, 0.48, 0.42, 0.35, 0.06, 0.04, 82),
    "future bass": (0.65, 0.75, 0.55, 0.05, 0.15, 0.10, 0.05, 150),
    "phonk": (0.68, 0.72, 0.35, 0.05, 0.10, 0.12, 0.15, 130),
    "drift phonk": (0.65, 0.75, 0.30, 0.04, 0.08, 0.12, 0.12, 135),

    # --- Rock ---
    "rock": (0.52, 0.72, 0.48, 0.18, 0.08, 0.20, 0.05, 125),
    "alternative rock": (0.50, 0.68, 0.40, 0.15, 0.10, 0.18, 0.05, 128),
    "indie rock": (0.50, 0.62, 0.45, 0.22, 0.10, 0.18, 0.04, 122),
    "punk rock": (0.42, 0.88, 0.45, 0.08, 0.05, 0.25, 0.06, 165),
    "metal": (0.35, 0.92, 0.25, 0.02, 0.08, 0.22, 0.06, 140),
    "hard rock": (0.45, 0.85, 0.40, 0.05, 0.06, 0.22, 0.05, 130),
    "classic rock": (0.50, 0.68, 0.55, 0.15, 0.08, 0.22, 0.05, 120),
    "grunge": (0.42, 0.78, 0.30, 0.10, 0.06, 0.20, 0.05, 120),
    "emo": (0.45, 0.72, 0.28, 0.12, 0.05, 0.18, 0.06, 135),
    "post-punk": (0.48, 0.65, 0.32, 0.15, 0.12, 0.18, 0.05, 130),
    "shoegaze": (0.38, 0.60, 0.35, 0.10, 0.20, 0.10, 0.03, 115),

    # --- Latin ---
    "reggaeton": (0.82, 0.75, 0.65, 0.08, 0.02, 0.14, 0.12, 95),
    "latin trap": (0.72, 0.68, 0.45, 0.08, 0.02, 0.12, 0.20, 135),
    "latin pop": (0.72, 0.68, 0.65, 0.15, 0.02, 0.14, 0.08, 115),
    "corrido": (0.58, 0.62, 0.55, 0.30, 0.04, 0.18, 0.08, 110),
    "corridos tumbados": (0.62, 0.58, 0.48, 0.28, 0.04, 0.16, 0.10, 112),
    "bachata": (0.72, 0.55, 0.65, 0.35, 0.03, 0.16, 0.06, 128),
    "salsa": (0.78, 0.72, 0.72, 0.25, 0.05, 0.25, 0.06, 180),

    # --- Caribbean ---
    "dancehall": (0.80, 0.70, 0.62, 0.10, 0.03, 0.16, 0.15, 100),
    "reggae": (0.72, 0.55, 0.65, 0.22, 0.04, 0.18, 0.08, 82),
    "afrobeats": (0.82, 0.68, 0.68, 0.12, 0.03, 0.15, 0.08, 108),
    "amapiano": (0.80, 0.58, 0.62, 0.10, 0.10, 0.12, 0.06, 112),
    "soca": (0.85, 0.82, 0.78, 0.08, 0.04, 0.22, 0.06, 130),

    # --- Jazz / Blues ---
    "jazz": (0.52, 0.40, 0.55, 0.55, 0.20, 0.22, 0.05, 120),
    "jazz rap": (0.62, 0.48, 0.50, 0.30, 0.08, 0.18, 0.22, 95),
    "blues": (0.52, 0.48, 0.42, 0.45, 0.08, 0.22, 0.06, 105),
    "smooth jazz": (0.58, 0.35, 0.60, 0.50, 0.25, 0.12, 0.04, 100),

    # --- Country ---
    "country": (0.58, 0.58, 0.62, 0.35, 0.04, 0.18, 0.05, 120),
    "country rap": (0.68, 0.65, 0.55, 0.18, 0.03, 0.16, 0.18, 125),

    # --- Other ---
    "gospel": (0.55, 0.58, 0.65, 0.30, 0.05, 0.25, 0.08, 105),
    "funk": (0.78, 0.72, 0.72, 0.15, 0.08, 0.20, 0.06, 110),
    "disco": (0.82, 0.72, 0.75, 0.10, 0.05, 0.15, 0.05, 118),
    "classical": (0.25, 0.30, 0.40, 0.85, 0.75, 0.12, 0.03, 100),
    "soundtrack": (0.30, 0.40, 0.38, 0.50, 0.50, 0.10, 0.04, 100),
}

# Keywords for fuzzy matching unknown genres
_KEYWORD_MODIFIERS: Dict[str, Dict[str, float]] = {
    "acoustic": {"acousticness": 0.25, "energy": -0.15},
    "chill": {"energy": -0.15, "valence": 0.05, "danceability": -0.10},
    "dark": {"valence": -0.15, "energy": 0.05},
    "melodic": {"valence": 0.10, "instrumentalness": 0.05, "speechiness": -0.05},
    "aggressive": {"energy": 0.15, "valence": -0.10, "speechiness": 0.05},
    "underground": {"energy": 0.05, "speechiness": 0.05},
    "alternative": {"acousticness": 0.05, "energy": -0.05},
    "indie": {"acousticness": 0.10, "energy": -0.08},
    "old school": {"acousticness": 0.08, "speechiness": 0.05},
    "new": {"energy": 0.05},
    "experimental": {"instrumentalness": 0.10, "valence": -0.05},
    "hard": {"energy": 0.15, "valence": -0.08},
    "soft": {"energy": -0.18, "acousticness": 0.12},
    "fast": {"energy": 0.10, "danceability": 0.05},
    "slow": {"energy": -0.12, "danceability": -0.08},
    "heavy": {"energy": 0.18, "acousticness": -0.10},
    "psychedelic": {"instrumentalness": 0.12, "valence": -0.05},
    "tropical": {"danceability": 0.10, "valence": 0.12},
    "summer": {"valence": 0.12, "energy": 0.05},
}

KEYS = [
    "danceability", "energy", "valence", "acousticness",
    "instrumentalness", "liveness", "speechiness", "tempo",
]


def _profile_for_genre(genre: str) -> Dict[str, float]:
    """Get audio feature profile for a single genre tag."""
    g = genre.lower().strip()

    # Exact match
    if g in GENRE_PROFILES:
        vals = GENRE_PROFILES[g]
        return dict(zip(KEYS, vals))

    # Try partial matches (e.g., "atl hip hop" matches "hip hop")
    best_match = None
    best_len = 0
    for known, vals in GENRE_PROFILES.items():
        if known in g and len(known) > best_len:
            best_match = vals
            best_len = len(known)
    if best_match:
        profile = dict(zip(KEYS, best_match))
        # Apply keyword modifiers
        for kw, mods in _KEYWORD_MODIFIERS.items():
            if kw in g:
                for feat, delta in mods.items():
                    if feat in profile:
                        profile[feat] = max(0.0, min(1.0, profile[feat] + delta))
        return profile

    # No match - apply keyword modifiers to a neutral baseline
    baseline = {
        "danceability": 0.55, "energy": 0.55, "valence": 0.45,
        "acousticness": 0.20, "instrumentalness": 0.05, "liveness": 0.14,
        "speechiness": 0.10, "tempo": 120,
    }
    for kw, mods in _KEYWORD_MODIFIERS.items():
        if kw in g:
            for feat, delta in mods.items():
                if feat in baseline:
                    baseline[feat] = max(0.0, min(1.0, baseline[feat] + delta))
    return baseline


def infer_audio_features(genres: List[str], weights: List[float] | None = None) -> Dict[str, float]:
    """
    Infer audio features from a list of genre tags.

    Args:
        genres: List of genre strings from Spotify artist data.
        weights: Optional weights for each genre (e.g., based on artist rank).
                 If None, earlier genres are weighted more heavily (position decay).

    Returns:
        Dict with the 8 audio feature keys.
    """
    if not genres:
        return {k: 0.0 for k in KEYS}

    if weights is None:
        # Position-based decay: first genres matter more
        weights = [1.0 / (1.0 + 0.3 * i) for i in range(len(genres))]

    total_weight = sum(weights)
    if total_weight == 0:
        return {k: 0.0 for k in KEYS}

    agg = {k: 0.0 for k in KEYS}
    matched = 0
    for genre, w in zip(genres, weights):
        profile = _profile_for_genre(genre)
        matched += 1
        for k in KEYS:
            agg[k] += profile[k] * w

    for k in KEYS:
        agg[k] = round(agg[k] / total_weight, 4)
        if k != "tempo":
            agg[k] = min(1.0, max(0.0, agg[k]))

    log.info(f"Inferred features from {matched}/{len(genres)} genres")
    return agg

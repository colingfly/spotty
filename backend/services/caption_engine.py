# backend/services/caption_engine.py
"""
Translates a Spotify taste profile (8 audio features + genres)
into ACE-Step generation parameters.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from models import UserTaste

# Map common Spotify genre prefixes to cleaner ACE-Step terms
GENRE_MAP = {
    "alt z": "alternative",
    "art pop": "art pop",
    "art rock": "art rock",
    "bedroom pop": "indie pop",
    "chicago rap": "hip hop",
    "classic rock": "classic rock",
    "cloud rap": "hip hop",
    "conscious hip hop": "conscious hip hop",
    "country": "country",
    "dance pop": "dance pop",
    "dark trap": "trap",
    "dream pop": "dream pop",
    "edm": "EDM",
    "electro house": "electro house",
    "electropop": "electropop",
    "emo": "emo",
    "emo rap": "emo rap",
    "folk": "folk",
    "funk": "funk",
    "garage rock": "garage rock",
    "grunge": "grunge",
    "hip hop": "hip hop",
    "house": "house",
    "indie": "indie",
    "indie folk": "indie folk",
    "indie pop": "indie pop",
    "indie rock": "indie rock",
    "jazz": "jazz",
    "k-pop": "K-pop",
    "latin": "latin",
    "lo-fi": "lo-fi",
    "metal": "metal",
    "modern rock": "modern rock",
    "neo soul": "neo soul",
    "new wave": "new wave",
    "pop": "pop",
    "pop punk": "pop punk",
    "pop rap": "pop rap",
    "pop rock": "pop rock",
    "post-punk": "post-punk",
    "progressive rock": "progressive rock",
    "psychedelic rock": "psychedelic rock",
    "punk": "punk",
    "r&b": "R&B",
    "rap": "rap",
    "reggae": "reggae",
    "reggaeton": "reggaeton",
    "rock": "rock",
    "shoegaze": "shoegaze",
    "singer-songwriter": "singer-songwriter",
    "ska": "ska",
    "soul": "soul",
    "southern hip hop": "southern hip hop",
    "synth-pop": "synth-pop",
    "techno": "techno",
    "trap": "trap",
    "underground hip hop": "underground hip hop",
}


def _map_genre(genre: str) -> str:
    """Map a Spotify genre to an ACE-Step-friendly term."""
    gl = genre.lower().strip()
    if gl in GENRE_MAP:
        return GENRE_MAP[gl]
    # Try prefix matching
    for prefix, mapped in GENRE_MAP.items():
        if gl.startswith(prefix):
            return mapped
    return genre


def _map_genres(genres: List[str], max_count: int = 5) -> str:
    """Map and deduplicate genres into a comma-separated string."""
    seen: set = set()
    mapped: List[str] = []
    for g in genres:
        m = _map_genre(g)
        ml = m.lower()
        if ml not in seen:
            seen.add(ml)
            mapped.append(m)
        if len(mapped) >= max_count:
            break
    return ", ".join(mapped) if mapped else "pop"


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def taste_to_caption(
    taste: UserTaste,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert a UserTaste profile into ACE-Step generation parameters.

    Returns a dict with keys matching ACE-Step's GenerationParams:
    - prompt: style caption
    - bpm: beats per minute
    - audio_duration: seconds
    - inference_steps: diffusion steps
    - batch_size: number of outputs
    """
    # Start with the taste values, apply overrides if given
    energy = taste.energy
    valence = taste.valence
    danceability = taste.danceability
    acousticness = taste.acousticness
    instrumentalness = taste.instrumentalness
    speechiness = taste.speechiness
    liveness = taste.liveness
    tempo = taste.tempo
    genres = list(taste.genres or [])

    if overrides:
        energy = overrides.get("energy", energy)
        valence = overrides.get("valence", valence)
        danceability = overrides.get("danceability", danceability)
        acousticness = overrides.get("acousticness", acousticness)
        instrumentalness = overrides.get("instrumentalness", instrumentalness)
        speechiness = overrides.get("speechiness", speechiness)
        liveness = overrides.get("liveness", liveness)
        tempo = overrides.get("tempo", tempo)
        if "genres" in overrides:
            genres = overrides["genres"]

    # Build genre string
    genre_str = _map_genres(genres)

    # Build descriptors from audio features
    descriptors: List[str] = []

    # Energy
    if energy > 0.7:
        descriptors.append("high-energy, powerful, driving")
    elif energy > 0.4:
        descriptors.append("moderate energy, steady")
    else:
        descriptors.append("calm, gentle, subdued")

    # Valence
    if valence > 0.65:
        descriptors.append("uplifting, bright, joyful")
    elif valence > 0.35:
        descriptors.append("balanced, contemplative")
    else:
        descriptors.append("melancholic, dark, moody")

    # Danceability
    if danceability > 0.7:
        descriptors.append("danceable, groovy, rhythmic")
    elif danceability > 0.4:
        descriptors.append("moderate groove")

    # Acousticness
    if acousticness > 0.6:
        descriptors.append("acoustic instrumentation, organic sound")
    elif acousticness < 0.3:
        descriptors.append("electronic production, synthesized")

    # Instrumentalness
    if instrumentalness > 0.5:
        descriptors.append("instrumental, minimal vocals")
    else:
        descriptors.append("vocal-forward, sung")

    # Speechiness
    if speechiness > 0.3:
        descriptors.append("spoken word elements, rap-influenced")

    # Liveness
    if liveness > 0.5:
        descriptors.append("live performance feel, raw")

    caption = f"{genre_str} track. {', '.join(descriptors)}."

    # Build params
    bpm = int(_clamp(tempo, 30, 300)) if tempo > 0 else 120

    params: Dict[str, Any] = {
        "prompt": caption,
        "lyrics": "[Instrumental]",
        "bpm": bpm,
        "audio_duration": 60,
        "infer_steps": 8,  # turbo mode
        "batch_size": 1,
    }

    # Apply any direct param overrides
    if overrides:
        for key in ("prompt", "lyrics", "bpm", "audio_duration", "infer_steps", "batch_size"):
            if key in overrides:
                params[key] = overrides[key]

    return params

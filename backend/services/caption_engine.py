# backend/services/caption_engine.py
"""
Compose ACE-Step generation briefs from a taste profile.

Two engines share one interface:
  - the Claude composer (services.llm) when credentials are configured
  - a deterministic template engine (this file) that always works offline

`compose()` is the single entry point used by the API. It applies presets
and slider overrides, asks Claude first, and falls back to the template
engine on any failure, tagging the result with which engine produced it.
"""
from __future__ import annotations

import logging
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from config import settings
from services.genre_analyzer import KEYS, infer_audio_features

log = logging.getLogger("spotty.compose")

FEATURE_KEYS = [k for k in KEYS]

MODES = ("taste", "mood", "lyrics", "fusion", "brief", "festival")

# Legacy feature_type names kept for the Library badges and old rows.
MODE_TO_FEATURE_TYPE = {
    "taste": "taste_to_track",
    "mood": "mood_slider",
    "lyrics": "lyric_mode",
    "fusion": "artist_fusion",
    "brief": "brief",
    "festival": "festival",
}


# --------------------------------------------------------------------------
# Presets: quick vibes that nudge the feature vector and add caption tags
# --------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, Any]] = {
    "late_night_drive": {
        "label": "Late Night Drive",
        "emoji": "🌃",
        "deltas": {"energy": -0.15, "valence": -0.10, "acousticness": -0.10, "danceability": 0.05},
        "tempo": 98,
        "tags": ["nocturnal", "wide synth pads", "spacious reverb", "steady pulse"],
    },
    "gym": {
        "label": "Gym",
        "emoji": "🏋️",
        "deltas": {"energy": 0.25, "danceability": 0.15, "valence": 0.05},
        "tempo": 142,
        "tags": ["punchy drums", "hype", "aggressive bass", "anthemic"],
    },
    "focus": {
        "label": "Deep Focus",
        "emoji": "🎯",
        "deltas": {"energy": -0.25, "instrumentalness": 0.6, "speechiness": -0.15, "danceability": -0.10},
        "tempo": 86,
        "tags": ["instrumental", "minimal", "ambient textures", "steady", "no vocals"],
        "vocals": False,
    },
    "heartbreak": {
        "label": "Heartbreak",
        "emoji": "💔",
        "deltas": {"valence": -0.30, "energy": -0.15, "acousticness": 0.20},
        "tempo": 74,
        "tags": ["intimate vocals", "piano", "melancholic", "slow build"],
    },
    "party": {
        "label": "House Party",
        "emoji": "🎉",
        "deltas": {"energy": 0.20, "danceability": 0.25, "valence": 0.25},
        "tempo": 124,
        "tags": ["club-ready", "big drops", "call-and-response hooks", "bright"],
    },
    "sunrise": {
        "label": "Sunrise",
        "emoji": "🌅",
        "deltas": {"valence": 0.30, "energy": -0.05, "acousticness": 0.15},
        "tempo": 108,
        "tags": ["warm", "hopeful", "shimmering guitars", "open chords"],
    },
    "rage": {
        "label": "Rage",
        "emoji": "🔥",
        "deltas": {"energy": 0.30, "valence": -0.20, "danceability": 0.05},
        "tempo": 150,
        "tags": ["distorted 808s", "screamed ad-libs", "chaotic synth leads", "mosh pit"],
    },
    "lofi_study": {
        "label": "Lo-fi Study",
        "emoji": "📚",
        "deltas": {"energy": -0.30, "acousticness": 0.20, "instrumentalness": 0.6, "speechiness": -0.1},
        "tempo": 80,
        "tags": ["dusty drums", "vinyl crackle", "mellow rhodes keys", "instrumental"],
        "vocals": False,
    },
}


def preset_catalog() -> List[Dict[str, Any]]:
    return [
        {"id": pid, "label": p["label"], "emoji": p["emoji"], "tags": p["tags"], "tempo": p["tempo"]}
        for pid, p in PRESETS.items()
    ]


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------

@dataclass
class ComposeRequest:
    mode: str = "taste"
    features: Dict[str, float] = field(default_factory=dict)
    genres: List[str] = field(default_factory=list)
    genre_weights: List[Dict[str, Any]] = field(default_factory=list)
    top_artists: List[str] = field(default_factory=list)
    overrides: Dict[str, float] = field(default_factory=dict)
    preset: Optional[str] = None
    brief: Optional[str] = None
    lyrics: Optional[str] = None
    lyrics_theme: Optional[str] = None
    want_vocals: bool = True
    fusion_artists: List[Dict[str, Any]] = field(default_factory=list)  # [{name, genres}]
    duration: int = 60
    use_llm: bool = True


@dataclass
class ComposeResult:
    title: str
    prompt: str
    lyrics: str
    bpm: int
    duration: int
    key_scale: Optional[str]
    tags: List[str]
    rationale: str
    engine: str  # llm | template
    features: Dict[str, float]
    mode: str
    preset: Optional[str]

    def to_acestep_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "prompt": self.prompt,
            "lyrics": self.lyrics or "[Instrumental]",
            "bpm": int(self.bpm),
            "audio_duration": int(self.duration),
            "infer_steps": settings.infer_steps,
            "batch_size": 1,
        }
        if self.key_scale:
            params["key_scale"] = self.key_scale
        return params

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["acestep_params"] = self.to_acestep_params()
        return d


# --------------------------------------------------------------------------
# Feature math
# --------------------------------------------------------------------------

def _clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


def apply_adjustments(base: Dict[str, float], overrides: Dict[str, Any], preset: Optional[str]) -> Dict[str, float]:
    """Preset deltas first, then explicit slider overrides win."""
    feats = {k: float(base.get(k, 0.0) or 0.0) for k in FEATURE_KEYS}
    if preset and preset in PRESETS:
        p = PRESETS[preset]
        for k, delta in p["deltas"].items():
            feats[k] = _clamp(feats[k] + delta)
        if p.get("tempo"):
            feats["tempo"] = float(p["tempo"])
    for k, v in (overrides or {}).items():
        if k not in FEATURE_KEYS:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        feats[k] = _clamp(fv, 30, 220) if k == "tempo" else _clamp(fv)
    return feats


def blend_artist_features(artists: List[Dict[str, Any]]) -> Dict[str, float]:
    """Average inferred features across several artists' genre tags."""
    genres: List[str] = []
    weights: List[float] = []
    for a in artists:
        for i, g in enumerate(a.get("genres") or []):
            genres.append(g)
            weights.append(1.0 / (1.0 + 0.4 * i))
    if not genres:
        return {}
    return infer_audio_features(genres, weights)


# --------------------------------------------------------------------------
# Template engine
# --------------------------------------------------------------------------

GENRE_MAP = {
    "alt z": "alternative", "bedroom pop": "indie pop", "chicago rap": "hip hop",
    "cloud rap": "cloud rap", "dark trap": "trap", "edm": "EDM", "k-pop": "K-pop",
    "r&b": "R&B", "rnb": "R&B", "lo-fi": "lo-fi", "lofi beats": "lo-fi",
    "synth-pop": "synth-pop", "synthpop": "synth-pop", "post-punk": "post-punk",
}

# Instrument palettes per genre family, used to make template captions concrete.
_FAMILY_INSTRUMENTS = [
    (("trap", "rage", "plugg", "drill", "rap", "hip hop"), ["booming 808s", "crisp rolling hi-hats", "dark piano loop", "sub bass"]),
    (("r&b", "soul", "neo soul"), ["rhodes keys", "smooth bass guitar", "finger snaps", "lush vocal harmonies"]),
    (("house", "techno", "edm", "dance", "electro"), ["four-on-the-floor kick", "sidechained synth chords", "filtered build-ups", "sub drops"]),
    (("indie", "rock", "garage", "shoegaze", "punk", "grunge", "emo"), ["jangly electric guitars", "live drum kit", "driving bass", "fuzz pedal"]),
    (("folk", "country", "singer-songwriter", "acoustic"), ["fingerpicked acoustic guitar", "upright bass", "soft brushed drums", "harmonica"]),
    (("pop", "dance pop", "electropop", "k-pop"), ["glossy synth stabs", "punchy drum machine", "layered vocal hooks", "bright plucks"]),
    (("jazz", "blues"), ["upright bass", "ride cymbal swing", "muted trumpet", "piano comping"]),
    (("ambient", "lo-fi", "chill"), ["tape-saturated keys", "soft vinyl crackle", "slow pads", "dusty drum loop"]),
    (("metal", "hardcore"), ["palm-muted guitars", "double-kick drums", "wall of distortion", "growled vocals"]),
    (("reggaeton", "latin", "dancehall", "afrobeats", "amapiano"), ["dembow rhythm", "log drums", "syncopated percussion", "warm bass"]),
]

_TITLE_WORDS = {
    "dark": ["Midnight", "Static", "Afterglow", "Velvet", "Undertow", "Neon Rain"],
    "bright": ["Golden Hour", "Open Sky", "Sunroof", "Bloom", "Daylight", "Paper Planes"],
    "mid": ["Drift", "Lowlight", "Echo Park", "Signal", "Halfway", "Silver Lining"],
}


def _map_genre(genre: str) -> str:
    gl = genre.lower().strip()
    return GENRE_MAP.get(gl, gl)


def _top_genres(genres: List[str], max_count: int = 4) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for g in genres:
        m = _map_genre(g)
        if m.lower() not in seen:
            seen.add(m.lower())
            out.append(m)
        if len(out) >= max_count:
            break
    return out or ["pop"]


def _instruments_for(genres: List[str]) -> List[str]:
    joined = " ".join(g.lower() for g in genres)
    for keys, palette in _FAMILY_INSTRUMENTS:
        if any(k in joined for k in keys):
            return palette[:3]
    return ["layered synths", "tight drums", "warm bass"]


def _descriptors(f: Dict[str, float], want_vocals: bool) -> List[str]:
    d: List[str] = []
    e, v, dn, ac, sp, lv = (f["energy"], f["valence"], f["danceability"], f["acousticness"], f["speechiness"], f["liveness"])
    d.append("high-energy, driving" if e > 0.7 else "mid-tempo, steady" if e > 0.4 else "calm, restrained")
    d.append("uplifting, bright" if v > 0.65 else "bittersweet, reflective" if v > 0.35 else "melancholic, moody")
    if dn > 0.7:
        d.append("groovy, head-nodding rhythm")
    elif dn < 0.4:
        d.append("loose, free-flowing rhythm")
    d.append("organic acoustic textures" if ac > 0.6 else "polished electronic production" if ac < 0.3 else "blended acoustic and electronic layers")
    if lv > 0.5:
        d.append("live room feel")
    if not want_vocals:
        d.append("instrumental")
    elif sp > 0.3:
        d.append("confident rap vocals, rhythmic delivery")
    elif f["instrumentalness"] > 0.5:
        d.append("sparse vocals, mostly instrumental")
    else:
        d.append("expressive lead vocal, catchy hook")
    return d


def _pick_key(valence: float, seed: str) -> str:
    rnd = random.Random(seed)
    roots = ["C", "D", "E", "F", "G", "A", "B", "F#", "Bb", "Eb"]
    quality = "major" if valence > 0.55 else "minor"
    return f"{rnd.choice(roots)} {quality}"


def _title(valence: float, genres: List[str], seed: str) -> str:
    rnd = random.Random(seed)
    bucket = "bright" if valence > 0.62 else "dark" if valence < 0.38 else "mid"
    return rnd.choice(_TITLE_WORDS[bucket])


def _template_lyrics(req: ComposeRequest, genres: List[str]) -> str:
    if not req.want_vocals:
        return "[Instrumental]"
    if req.lyrics and req.lyrics.strip():
        text = req.lyrics.strip()
        if not re.search(r"\[(verse|chorus|intro|bridge|outro|pre-chorus)", text, re.I):
            text = "[verse]\n" + text
        return text
    if req.lyrics_theme:
        theme = req.lyrics_theme.strip()
        return (
            f"[verse]\nCity lights are humming, {theme} on my mind\n"
            f"Every street remembers what I left behind\n\n"
            f"[chorus]\n{theme.capitalize()}, {theme}, say it twice\n"
            f"Hold it in the chorus till it feels like mine\n\n"
            f"[verse]\nLate replies and headlights, counting every sign\n"
            f"If the night is listening, give me one more line\n\n"
            f"[chorus]\n{theme.capitalize()}, {theme}, say it twice\n"
            f"Hold it in the chorus till it feels like mine"
        )
    return "[Instrumental]"


def template_compose(req: ComposeRequest, feats: Dict[str, float]) -> ComposeResult:
    genres = list(req.genres)
    if req.mode in ("fusion", "festival") and req.fusion_artists:
        fused: List[str] = []
        for a in req.fusion_artists:
            fused.extend((a.get("genres") or [])[:3])
        genres = fused or genres

    top = _top_genres(genres)
    instruments = _instruments_for(top)
    descriptors = _descriptors(feats, req.want_vocals)
    preset_tags = PRESETS.get(req.preset or "", {}).get("tags", [])

    parts: List[str] = [", ".join(top)] + instruments + descriptors + list(preset_tags)
    if req.mode == "brief" and req.brief:
        parts.insert(1, req.brief.strip().rstrip("."))
    if req.mode == "festival":
        parts.append("festival main stage energy, crowd-ready")
    if req.mode == "fusion":
        parts.append("genre-blending, cohesive crossover")

    seen: set = set()
    clean: List[str] = []
    for p in parts:
        pl = p.lower()
        if pl and pl not in seen:
            seen.add(pl)
            clean.append(p)
    caption = ", ".join(clean)

    seed = f"{req.mode}|{caption}|{req.brief}|{req.lyrics_theme}"
    tempo = feats.get("tempo") or 120
    bpm = int(_clamp(tempo, 40, 220))

    rationale_bits = [f"Built around {top[0]}"]
    if len(top) > 1:
        rationale_bits.append(f"with {top[1]} colour")
    if req.preset in PRESETS:
        rationale_bits.append(f"shaped by the {PRESETS[req.preset]['label']} preset")
    if req.mode == "mood" and req.overrides:
        rationale_bits.append("and your slider moves")

    return ComposeResult(
        title=_title(feats["valence"], top, seed),
        prompt=caption,
        lyrics=_template_lyrics(req, top),
        bpm=bpm,
        duration=req.duration,
        key_scale=_pick_key(feats["valence"], seed),
        tags=[t for t in (top[:2] + list(preset_tags)[:2])],
        rationale=" ".join(rationale_bits) + ".",
        engine="template",
        features=feats,
        mode=req.mode,
        preset=req.preset,
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def compose(req: ComposeRequest) -> ComposeResult:
    if req.mode not in MODES:
        raise ValueError(f"unknown mode: {req.mode}")

    base = dict(req.features)
    if req.mode in ("fusion", "festival") and req.fusion_artists:
        blended = blend_artist_features(req.fusion_artists)
        if blended:
            # Blend 70% artists / 30% listener so the result still feels like theirs
            base = {k: 0.7 * blended.get(k, 0) + 0.3 * float(base.get(k, 0) or 0) for k in FEATURE_KEYS}

    preset = req.preset if req.preset in PRESETS else None
    feats = apply_adjustments(base, req.overrides, preset)
    if preset and PRESETS[preset].get("vocals") is False:
        req.want_vocals = False

    req.duration = int(max(15, min(settings.max_duration_seconds, req.duration or settings.default_duration_seconds)))

    if req.use_llm:
        try:
            from services import llm

            if llm.available():
                payload = {
                    "mode": req.mode,
                    "features": {k: round(v, 3) for k, v in feats.items()},
                    "baseline_features": {k: round(float(req.features.get(k, 0) or 0), 3) for k in FEATURE_KEYS},
                    "overrides": req.overrides,
                    "genre_weights": req.genre_weights[:12] if req.genre_weights else [{"genre": g, "weight": 1.0} for g in req.genres[:12]],
                    "top_artists": req.top_artists[:15],
                    "preset": {"id": preset, **{k: PRESETS[preset][k] for k in ("label", "tags")}} if preset else None,
                    "brief": req.brief,
                    "lyrics": req.lyrics,
                    "lyrics_theme": req.lyrics_theme,
                    "want_vocals": req.want_vocals,
                    "fusion_artists": req.fusion_artists[:8],
                    "duration_seconds": req.duration,
                }
                out = llm.compose_track(payload)
                return ComposeResult(
                    title=out["title"],
                    prompt=out["prompt"],
                    lyrics=out["lyrics"],
                    bpm=out["bpm"],
                    duration=req.duration,
                    key_scale=out.get("key_scale"),
                    tags=out.get("tags") or [],
                    rationale=out.get("rationale") or "",
                    engine="llm",
                    features=feats,
                    mode=req.mode,
                    preset=preset,
                )
        except Exception as e:  # LLMUnavailable or anything unexpected
            log.warning("LLM compose failed (%s); using template engine", e)

    return template_compose(req, feats)


# --------------------------------------------------------------------------
# Backwards-compatible shim used by older code paths/tests
# --------------------------------------------------------------------------

def taste_to_caption(taste, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Legacy: return raw ACE-Step params from a UserTaste row (template engine only)."""
    overrides = dict(overrides or {})
    lyrics = overrides.pop("lyrics", None)
    req = ComposeRequest(
        mode="lyrics" if lyrics else ("mood" if overrides else "taste"),
        features=taste.as_features(),
        genres=list(taste.genres or []),
        overrides=overrides,
        lyrics=lyrics,
        want_vocals=bool(lyrics),
        use_llm=False,
    )
    result = compose(req)
    params = result.to_acestep_params()
    for key in ("prompt", "bpm", "audio_duration", "infer_steps", "batch_size"):
        if key in overrides:
            params[key] = overrides[key]
    return params

# backend/services/llm.py
"""
Claude-powered composer.

Turns a listener's taste profile (8 audio features + weighted genres + top
artists) plus a generation mode into a production-grade ACE-Step brief:
a dense style caption, structured lyrics (or [Instrumental]), BPM, key, and
a track title. Also writes the "Sound DNA" narrative shown on the dashboard.

Everything here is optional. If no Anthropic credentials are configured, or
a call fails, callers fall back to the template engine in caption_engine.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config import settings

log = logging.getLogger("spotty.llm")

_KEY_RE = re.compile(r"^[A-G][#b]? (major|minor)$")


class LLMUnavailable(RuntimeError):
    """Raised when Claude cannot be used for this request (no key, refusal, API error)."""


# --------------------------------------------------------------------------
# Output schemas (structured outputs via messages.parse)
# --------------------------------------------------------------------------

class TrackBrief(BaseModel):
    title: str = Field(description="Evocative track title, 1-5 words, no quotes.")
    prompt: str = Field(
        description=(
            "ACE-Step style caption: 12-30 comma-separated descriptors covering genre, "
            "sub-genre, instrumentation, drum character, production texture, mood, era, "
            "and vocal style (or 'instrumental'). No sentences, no artist names."
        )
    )
    lyrics: str = Field(
        description=(
            "Either the exact string [Instrumental], or full lyrics using section tags "
            "[intro] [verse] [pre-chorus] [chorus] [bridge] [outro] on their own lines."
        )
    )
    bpm: int = Field(ge=40, le=220)
    key_scale: str = Field(description="Musical key like 'F# minor' or 'C major'.")
    tags: List[str] = Field(description="3-6 short vibe tags for the UI, lowercase.")
    rationale: str = Field(description="One or two sentences on why this fits the listener. Second person.")


class SoundDNA(BaseModel):
    headline: str = Field(description="Punchy 3-7 word name for this listener's taste.")
    summary: str = Field(description="2-3 sentences describing their sound, second person, specific and warm.")
    signature_sounds: List[str] = Field(description="4-6 short phrases: instruments, textures, production habits.")
    eras: List[str] = Field(description="1-3 eras or scenes their taste draws from.")
    persona: str = Field(description="A single playful listener archetype, 2-5 words.")
    suggested_modes: List[str] = Field(
        description="2-3 suggestions phrased as 'Try X: because Y', each under 18 words."
    )


class LyricSheet(BaseModel):
    title: str
    lyrics: str = Field(description="Full lyrics with [verse]/[chorus]/[bridge] tags, 12-28 lines.")


# --------------------------------------------------------------------------
# Prompts (kept stable so prompt caching can hit)
# --------------------------------------------------------------------------

COMPOSER_SYSTEM = """You are the composer behind trill, an app that turns a person's Spotify listening DNA into original music with the ACE-Step 1.5 text-to-music model.

You write generation briefs for ACE-Step. What makes ACE-Step output great:
- Captions are comma-separated descriptor lists, not prose. Mix: genre + sub-genre, 2-4 concrete instruments, drum character (e.g. "crisp trap hi-hats", "brushed snare"), production texture ("tape saturation", "wide stereo synth pads", "lo-fi crackle"), mood words, an era or scene reference ("late-90s", "Atlanta 2016", "Berlin club"), and vocal description ("breathy female vocal", "autotuned melodic rap", "instrumental").
- Be specific and sonic. "Dreamy" is weak; "shimmering reverb-soaked guitars, hazy vocal doubles" is strong.
- Never name real artists, bands, or songs in the caption or lyrics. Translate influences into sound.
- Lyrics must use section tags on their own lines: [intro], [verse], [pre-chorus], [chorus], [bridge], [outro]. Keep lines singable, concrete imagery over abstraction, a chorus that repeats a hook. For instrumentals return exactly [Instrumental].
- BPM must match the genre (trap 130-160 half-time feel, house 120-128, boom bap 85-95, drill 140-145, ballads 60-80, drum and bass 170-176).
- Choose a key that fits the mood (minor for melancholy, major for bright, modal choices welcome).

You receive the listener's audio-feature profile (0-1 scales, tempo in BPM), weighted genres, top artists, and a mode:
- taste: a track that could sit in the middle of their library.
- mood: they moved the sliders; the overrides are intent, honor them over the baseline.
- lyrics: they supplied lyrics (or a theme). Keep provided lyrics verbatim except fixing section tags. If only a theme is given, write the lyrics.
- fusion: blend the listed artists' sounds into one coherent track. Describe the blend sonically.
- brief: free-text creative direction. The brief wins; the profile adds flavor.
- festival: a lineup from a concert poster. Capture the night's shared energy.

If a preset is present, lean into its tags. Respect requested vocals flag: when vocals are off, return [Instrumental] and describe the track as instrumental."""

DNA_SYSTEM = """You are trill's music critic. You write short, specific, warm profiles of a listener's taste from their Spotify data: audio features (0-1, tempo in BPM), weighted genre tags, and top artists.

Write like a sharp friend who works at a record store: concrete sounds, eras, scenes, textures. Second person. No generic praise, no hedging, no lists of artist names recited back. You may reference artists sparingly to anchor a point. Keep everything compact enough to fit on one card."""

LYRICS_SYSTEM = """You write lyrics for trill, which generates music with ACE-Step 1.5. Produce complete, singable lyrics with section tags on their own lines ([intro] [verse] [pre-chorus] [chorus] [bridge] [outro]). Match the listener's genres and the requested theme and mood: rap-leaning profiles get denser internal rhyme and bars; pop gets a tight repeated hook; folk gets narrative verses. Concrete imagery, a chorus that repeats, no real artist or song names, no explicit slurs."""


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

_client = None
_client_checked = False


def _get_client():
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not settings.llm_enabled:
        log.info("LLM composer disabled via LLM_ENABLED")
        return None
    has_creds = bool(settings.anthropic_api_key or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    if not has_creds:
        log.info("No Anthropic credentials; using template composer")
        return None
    try:
        import anthropic

        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key or None,
            timeout=90.0,
            max_retries=2,
        )
        log.info("LLM composer ready (model=%s)", settings.anthropic_model)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("Could not initialize Anthropic client: %s", e)
        _client = None
    return _client


def available() -> bool:
    return _get_client() is not None


def _parse(system: str, user_payload: Dict[str, Any], schema: type[BaseModel], effort: str = "low", max_tokens: int = 4096):
    """Run one structured request. Raises LLMUnavailable on any failure."""
    client = _get_client()
    if client is None:
        raise LLMUnavailable("llm_not_configured")

    import anthropic

    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)}],
            output_format=schema,
            output_config={"effort": effort},
        )
    except anthropic.RateLimitError as e:
        log.warning("Claude rate limited: %s", e)
        raise LLMUnavailable("rate_limited") from e
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s: %s", e.status_code, e.message)
        raise LLMUnavailable(f"api_error_{e.status_code}") from e
    except anthropic.APIConnectionError as e:
        log.warning("Claude connection error: %s", e)
        raise LLMUnavailable("connection_error") from e

    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        log.warning("Claude declined request: %s", detail)
        raise LLMUnavailable("refusal")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("truncated")

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise LLMUnavailable("no_parsed_output")
    usage = getattr(response, "usage", None)
    if usage is not None:
        log.info(
            "Claude ok: in=%s cached=%s out=%s",
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "cache_read_input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )
    return parsed


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def compose_track(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload keys: mode, features, genre_weights, top_artists, overrides, preset,
    preset_tags, brief, lyrics, lyrics_theme, want_vocals, fusion_artists, duration.
    Returns a dict shaped like caption_engine.ComposeResult (minus engine).
    """
    brief: TrackBrief = _parse(COMPOSER_SYSTEM, payload, TrackBrief, effort="low")

    lyrics = (brief.lyrics or "").strip() or "[Instrumental]"
    if not payload.get("want_vocals", True):
        lyrics = "[Instrumental]"
    elif lyrics.lower().strip("[] ") == "instrumental":
        lyrics = "[Instrumental]"

    key_scale = brief.key_scale.strip() if brief.key_scale else None
    if key_scale and not _KEY_RE.match(key_scale):
        key_scale = None

    return {
        "title": brief.title.strip()[:80] or "Untitled",
        "prompt": brief.prompt.strip(),
        "lyrics": lyrics,
        "bpm": int(max(40, min(220, brief.bpm))),
        "key_scale": key_scale,
        "tags": [t.strip().lower() for t in brief.tags if t.strip()][:6],
        "rationale": brief.rationale.strip(),
    }


def sound_dna(profile_payload: Dict[str, Any]) -> Dict[str, Any]:
    dna: SoundDNA = _parse(DNA_SYSTEM, profile_payload, SoundDNA, effort="low", max_tokens=2048)
    return dna.model_dump()


def write_lyrics(payload: Dict[str, Any]) -> Dict[str, str]:
    sheet: LyricSheet = _parse(LYRICS_SYSTEM, payload, LyricSheet, effort="low", max_tokens=3000)
    return {"title": sheet.title.strip()[:80], "lyrics": sheet.lyrics.strip()}


def status() -> Dict[str, Any]:
    return {
        "enabled": settings.llm_enabled,
        "configured": available(),
        "model": settings.anthropic_model if available() else None,
    }

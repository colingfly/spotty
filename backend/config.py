# backend/config.py
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

log = logging.getLogger("spotty.config")

_HERE = os.path.dirname(os.path.abspath(__file__))


def _safe_int(val: Optional[str], default: int) -> int:
    try:
        return int(str(val))
    except (TypeError, ValueError):
        return default


def _safe_bool(val: Optional[str], default: bool) -> bool:
    if val is None or val == "":
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _csv(s: Optional[str], default: List[str]) -> List[str]:
    if not s:
        return default
    return [part.strip() for part in s.split(",") if part.strip()]


def _stable_secret() -> str:
    """
    Return FLASK_SECRET_KEY, or a key persisted to backend/.secret_key.

    Session tokens and OAuth state are signed with this key. A random
    per-process key would invalidate every login on restart and break
    multi-worker deployments, so we persist one for local development.
    Production should always set FLASK_SECRET_KEY explicitly.
    """
    env = os.getenv("FLASK_SECRET_KEY", "").strip()
    if env:
        return env
    path = os.path.join(_HERE, ".secret_key")
    try:
        with open(path, "r", encoding="utf-8") as fp:
            key = fp.read().strip()
            if len(key) >= 32:
                return key
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32)
    try:
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(key)
        log.warning("FLASK_SECRET_KEY not set; generated one at %s", path)
    except OSError:
        log.warning("FLASK_SECRET_KEY not set and could not persist a key; sessions reset on restart")
    return key


@dataclass(frozen=True)
class Settings:
    # App
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = _safe_int(os.getenv("APP_PORT", "8888"), 8888)
    secret_key: str = field(default_factory=_stable_secret)
    env: str = os.getenv("APP_ENV", "development")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "") or f"sqlite:///{os.path.join(_HERE, 'spotty.db')}"

    # Spotify OAuth
    spotify_client_id: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    spotify_client_secret: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    spotify_redirect_uri: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    spotify_scope: str = os.getenv("SPOTIFY_SCOPE", "user-top-read user-read-private")

    # Session tokens (seconds). Default 30 days.
    session_ttl_seconds: int = _safe_int(os.getenv("SESSION_TTL_SECONDS", str(30 * 24 * 3600)), 30 * 24 * 3600)

    # Frontend + CORS
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5180")
    cors_origins: List[str] = field(default_factory=list)  # set in __post_init__

    # Last.fm (genre tags). The default is a widely published demo key; set your own.
    lastfm_api_key: str = os.getenv("LASTFM_API_KEY", "b25b959554ed76058ac220b7b2e0a026")

    # OCR
    tesseract_cmd: Optional[str] = os.getenv("TESSERACT_CMD")

    # ACE-Step
    acestep_api_url: str = os.getenv("ACESTEP_API_URL", "http://127.0.0.1:8001")
    audio_output_dir: str = os.getenv("AUDIO_OUTPUT_DIR", os.path.join(_HERE, "audio_output"))
    audio_upload_dir: str = os.getenv("AUDIO_UPLOAD_DIR", os.path.join(_HERE, "audio_uploads"))
    default_duration_seconds: int = _safe_int(os.getenv("DEFAULT_DURATION_SECONDS", "60"), 60)
    max_duration_seconds: int = _safe_int(os.getenv("MAX_DURATION_SECONDS", "240"), 240)
    max_variations: int = _safe_int(os.getenv("MAX_VARIATIONS", "3"), 3)
    infer_steps: int = _safe_int(os.getenv("ACESTEP_INFER_STEPS", "8"), 8)

    # Background completion worker
    worker_enabled: bool = _safe_bool(os.getenv("WORKER_ENABLED"), True)
    worker_interval_seconds: int = _safe_int(os.getenv("WORKER_INTERVAL_SECONDS", "3"), 3)

    # Claude (LLM composer). Leave the key empty to run on the template engine only.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    llm_enabled: bool = _safe_bool(os.getenv("LLM_ENABLED"), True)

    # Rate limits (flask-limiter syntax)
    rate_limit_generate: str = os.getenv("RATE_LIMIT_GENERATE", "12 per minute")
    rate_limit_llm: str = os.getenv("RATE_LIMIT_LLM", "20 per minute")
    rate_limit_default: str = os.getenv("RATE_LIMIT_DEFAULT", "240 per minute")

    # Misc
    max_upload_mb: int = _safe_int(os.getenv("MAX_UPLOAD_MB", "8"), 8)

    def __post_init__(self):
        object.__setattr__(
            self,
            "cors_origins",
            _csv(os.getenv("CORS_ALLOW_ORIGINS"), [self.frontend_url]),
        )

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("prod", "production")


settings = Settings()

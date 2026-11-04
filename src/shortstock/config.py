"""Paths and settings.

Settings are stored in the local SQLite database so they can be edited from the UI or the
CLI. Environment variables act as fallbacks, which is handy for Docker and CI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def home() -> Path:
    """Root folder for the database, runs and the stock cache (``SHORTSTOCK_HOME``)."""
    path = Path(os.environ.get("SHORTSTOCK_HOME", Path.home() / ".shortstock")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    return home() / "runs"


def uploads_dir() -> Path:
    return home() / "uploads"


def stock_dir() -> Path:
    """Downloaded stock clips, reused across runs."""
    return home() / "stock"


@dataclass(frozen=True, slots=True)
class SettingSpec:
    env: str
    default: str = ""
    secret: bool = False
    description: str = ""


SETTINGS: dict[str, SettingSpec] = {
    # Voice
    "tts_provider": SettingSpec("SHORTSTOCK_TTS_PROVIDER", "elevenlabs", description="elevenlabs or fish"),
    "elevenlabs_api_key": SettingSpec("ELEVENLABS_API_KEY", secret=True, description="ElevenLabs API key"),
    "elevenlabs_voice_id": SettingSpec(
        "ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb", description="Default ElevenLabs voice"
    ),
    "elevenlabs_model": SettingSpec(
        "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2", description="ElevenLabs model id"
    ),
    "fish_api_key": SettingSpec("FISH_API_KEY", secret=True, description="Fish Audio API key"),
    "fish_voice_id": SettingSpec("FISH_VOICE_ID", description="Default Fish Audio voice (model id)"),
    "fish_model": SettingSpec("FISH_MODEL", "s2.1-pro", description="Fish Audio TTS model"),
    # Footage
    "pexels_api_key": SettingSpec("PEXELS_API_KEY", secret=True, description="Pexels API key for footage"),
    # Optional AI for footage search terms
    "llm_provider": SettingSpec("SHORTSTOCK_LLM_PROVIDER", "openrouter", description="LLM provider"),
    "openrouter_api_key": SettingSpec(
        "OPENROUTER_API_KEY", secret=True, description="Optional. Writes better footage searches"
    ),
    "llm_model": SettingSpec(
        "SHORTSTOCK_LLM_MODEL", "google/gemini-3.8-flash", description="Model that writes footage searches"
    ),
    # Publishing
    "buffer_api_key": SettingSpec("BUFFER_API_KEY", secret=True, description="Buffer API key"),
    "buffer_organization_id": SettingSpec(
        "BUFFER_ORGANIZATION_ID", description="Buffer organization (auto-picked if you have one)"
    ),
    "s3_endpoint_url": SettingSpec(
        "SHORTSTOCK_S3_ENDPOINT_URL", description="S3-compatible endpoint (R2, B2, MinIO). Empty for AWS"
    ),
    "s3_region": SettingSpec("SHORTSTOCK_S3_REGION", "auto", description="S3 region"),
    "s3_bucket": SettingSpec("SHORTSTOCK_S3_BUCKET", description="Bucket that hosts videos for Buffer"),
    "s3_access_key_id": SettingSpec("SHORTSTOCK_S3_ACCESS_KEY_ID", secret=True, description="S3 key id"),
    "s3_secret_access_key": SettingSpec(
        "SHORTSTOCK_S3_SECRET_ACCESS_KEY", secret=True, description="S3 secret"
    ),
    "s3_public_base_url": SettingSpec(
        "SHORTSTOCK_S3_PUBLIC_BASE_URL",
        description="Public URL of the bucket. Empty uses 7-day signed links",
    ),
}


def get_setting(key: str) -> str:
    """Database value, then environment variable, then default."""
    from shortstock import db

    spec = SETTINGS[key]
    value = db.get_setting(key)
    if value:
        return value
    return os.environ.get(spec.env, spec.default)


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"{value[:3]}••••{value[-4:]}"

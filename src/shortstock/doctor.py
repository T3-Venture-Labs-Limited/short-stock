"""Environment checks shared by `shortstock doctor` and the UI."""

from __future__ import annotations

from shortstock.config import get_setting
from shortstock.media import find_ffmpeg, install_hint
from shortstock.publish import storage_configured

LABELS = {
    "ffmpeg": "FFmpeg",
    "captions": "Captions",
    "voice": "Voice",
    "footage": "Footage",
    "ai": "AI footage search",
    "buffer": "Buffer",
    "storage": "Storage",
}


def checks() -> list[dict]:
    found = find_ffmpeg()
    ffmpeg, libass = found.ffmpeg, found.libass
    provider = get_setting("tts_provider") or "elevenlabs"
    voice_key = get_setting(f"{provider}_api_key")
    voice_id = get_setting(f"{provider}_voice_id")
    names = {"elevenlabs": "ElevenLabs", "fish": "Fish Audio"}
    voice_detail = (
        f"{names[provider]} ready"
        if voice_key and voice_id
        else f"add a {names[provider]} API key"
        if not voice_key
        else f"pick a default {names[provider]} voice"
    )
    pexels = bool(get_setting("pexels_api_key"))
    return [
        _check(
            "ffmpeg",
            bool(ffmpeg and found.ffprobe),
            True,
            ffmpeg if ffmpeg and found.ffprobe else f"ffmpeg and ffprobe not found. {install_hint()}",
        ),
        _check(
            "captions",
            libass,
            True,
            "ffmpeg has libass"
            if libass
            else f"this ffmpeg can't draw captions (it has no libass). {install_hint()}",
        ),
        _check("voice", bool(voice_key and voice_id), True, voice_detail),
        _check("footage", pexels, True, "Pexels key set" if pexels else "add a free Pexels API key"),
        _check(
            "ai",
            bool(get_setting("openrouter_api_key")),
            False,
            "OpenRouter writes footage searches"
            if get_setting("openrouter_api_key")
            else "optional: an OpenRouter key picks better footage than keywords",
        ),
        _check(
            "buffer",
            bool(get_setting("buffer_api_key")),
            False,
            "Buffer key set" if get_setting("buffer_api_key") else "optional: add a Buffer key to post",
        ),
        _check(
            "storage",
            storage_configured(),
            False,
            "S3 storage set" if storage_configured() else "optional: needed to publish to Buffer",
        ),
    ]


def _check(name: str, ok: bool, required: bool, detail: str) -> dict:
    return {"name": name, "label": LABELS[name], "ok": ok, "required": required, "detail": detail}

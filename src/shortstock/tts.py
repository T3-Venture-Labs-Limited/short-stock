"""Text to speech with word timestamps: ElevenLabs and Fish Audio.

Both providers return timing data with the audio, so cuts and captions line up with the words
without running a separate speech-recognition model.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from shortstock.config import get_setting
from shortstock.media import probe_duration, run_ffmpeg

logger = logging.getLogger(__name__)

CHUNK_CHARS = 3500
PROVIDERS = ("elevenlabs", "fish")


class TTSError(RuntimeError):
    pass


def _error(provider: str, response: httpx.Response) -> TTSError:
    """Turn a provider error into one plain sentence a person can act on."""
    status = response.status_code
    if status in (401, 403):
        return TTSError(f"{provider} rejected the API key. Check it in Settings, under Voice.")
    message = _message(response)
    if status == 402 or "credit" in message.lower() or "quota" in message.lower():
        hint = (
            " Top up at fish.audio, or choose the free model (S2.1 Pro Free) in Settings, under Voice."
            if provider == "Fish Audio"
            else " Top up your plan, or switch to Fish Audio in the Voice menu."
        )
        return TTSError(f"Your {provider} account is out of credit.{hint}")
    if status == 429:
        return TTSError(f"{provider} is rate limiting this key. Wait a minute and try again.")
    if status >= 500:
        return TTSError(f"{provider} is having problems right now ({status}). Try again in a few minutes.")
    return TTSError(
        f"{provider} said: {message[:240]}" if message else f"{provider} returned error {status}."
    )


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("detail") or ""
    return str(detail or "").strip()


@dataclass(slots=True)
class Speech:
    audio: bytes
    words: list[dict]  # {"word", "start", "end"} in seconds


class Voice(Protocol):
    def speak(self, text: str) -> Speech: ...


class ElevenLabs:
    url = "https://api.elevenlabs.io"

    def __init__(self, api_key: str, voice_id: str, model: str, speed: float = 1.0, transport=None):
        if not api_key:
            raise TTSError("Add an ElevenLabs API key in Settings to use ElevenLabs voices")
        if not voice_id:
            raise TTSError("Pick an ElevenLabs voice")
        self.voice_id, self.model, self.speed = voice_id, model, speed
        self._client = httpx.Client(
            base_url=self.url, headers={"xi-api-key": api_key}, timeout=180, transport=transport
        )

    def speak(self, text: str) -> Speech:
        response = self._client.post(
            f"/v1/text-to-speech/{self.voice_id}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            json={
                "text": text,
                "model_id": self.model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": self.speed},
            },
        )
        if response.status_code >= 400:
            raise _error("ElevenLabs", response)
        payload = response.json()
        alignment = payload.get("alignment") or payload.get("normalized_alignment") or {}
        return Speech(base64.b64decode(payload["audio_base64"]), words_from_characters(alignment))

    def voices(self) -> list[dict]:
        response = self._client.get("/v1/voices")
        if response.status_code >= 400:
            raise _error("ElevenLabs", response)
        return [
            {
                "id": v["voice_id"],
                "name": v.get("name", v["voice_id"]),
                "description": ", ".join(str(x) for x in (v.get("labels") or {}).values() if x),
                "preview_url": v.get("preview_url"),
            }
            for v in response.json().get("voices", [])
        ]


_FISH_CACHE: dict[tuple, tuple[float, dict]] = {}


class Fish:
    url = "https://api.fish.audio"

    def __init__(self, api_key: str, voice_id: str, model: str, speed: float = 1.0, transport=None):
        if not api_key:
            raise TTSError("Add a Fish Audio API key in Settings to use Fish voices")
        if not voice_id:
            raise TTSError("Pick a Fish Audio voice")
        self.voice_id, self.model, self.speed = voice_id, model, speed
        self._client = httpx.Client(
            base_url=self.url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300,
            transport=transport,
        )

    def speak(self, text: str) -> Speech:
        body = {
            "text": text,
            "reference_id": self.voice_id,
            "format": "mp3",
            "mp3_bitrate": 192,
            "sample_rate": 44100,
            "latency": "normal",
            "normalize": True,
            "prosody": {"speed": self.speed, "volume": 0, "normalize_loudness": True},
        }
        audio = bytearray()
        alignments: dict[int, tuple[float, dict]] = {}  # chunk_seq -> latest alignment for that chunk
        with self._client.stream(
            "POST", "/v1/tts/stream/with-timestamp", json=body, headers={"model": self.model}
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise _error("Fish Audio", response)
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if event.get("audio_base64"):
                    audio += base64.b64decode(event["audio_base64"])
                if event.get("alignment"):
                    # Alignment can repeat for the same chunk; keep the latest per chunk.
                    seq = int(event.get("chunk_seq") or 0)
                    alignments[seq] = (float(event.get("chunk_audio_offset_sec") or 0), event["alignment"])
        if not audio:
            raise TTSError("Fish Audio returned no audio")
        words = []
        for seq in sorted(alignments):
            offset, alignment = alignments[seq]
            for seg in alignment.get("segments", []):
                text_seg = str(seg.get("text", "")).strip()
                if text_seg:
                    words.append(
                        {
                            "word": text_seg,
                            "start": round(offset + float(seg["start"]), 3),
                            "end": round(offset + float(seg["end"]), 3),
                        }
                    )
        return Speech(bytes(audio), words)

    def voices(self, search: str = "", current: str | None = None) -> list[dict]:
        """Your own voices (or popular ones if you have none), or a library search.

        The current voice is always included so the picker can show its name.
        """
        if search:
            items = self._models({"title": search})
        else:
            items = self._models({"self": "true"}) or self._models({"language": "en"})
        if current and not any(item["_id"] == current for item in items):
            found = self._cached(f"/model/{current}", {})
            if found:
                items.insert(0, found)
        return [
            {
                "id": item["_id"],
                "name": item.get("title") or item["_id"],
                "description": ", ".join(item.get("languages") or []),
                "preview_url": (item.get("samples") or [{}])[0].get("audio") if item.get("samples") else None,
            }
            for item in items
        ]

    def _models(self, params: dict) -> list[dict]:
        found = self._cached("/model", {"page_size": 50, "sort_by": "task_count", **params}, required=True)
        return list(found.get("items", []))

    def _cached(self, path: str, params: dict, required: bool = False) -> dict:
        """Fish's voice library is slow (about a second a call) and rarely changes, so keep it ten minutes."""
        key = (self._client.headers.get("Authorization"), path, tuple(sorted(params.items())))
        hit = _FISH_CACHE.get(key)
        if hit and time.monotonic() - hit[0] < 600:
            return hit[1]
        response = self._client.get(path, params=params)
        if response.status_code >= 400:
            if required:
                raise _error("Fish Audio", response)
            return {}
        _FISH_CACHE[key] = (time.monotonic(), response.json())
        return _FISH_CACHE[key][1]


def get_voice(provider: str | None = None, voice_id: str | None = None, speed: float = 1.0):
    provider = provider or get_setting("tts_provider") or "elevenlabs"
    if provider == "elevenlabs":
        return ElevenLabs(
            get_setting("elevenlabs_api_key"),
            voice_id or get_setting("elevenlabs_voice_id"),
            get_setting("elevenlabs_model"),
            speed,
        )
    if provider == "fish":
        return Fish(
            get_setting("fish_api_key"),
            voice_id or get_setting("fish_voice_id"),
            get_setting("fish_model"),
            speed,
        )
    raise TTSError(f"Unknown voice provider '{provider}'. Use one of: {', '.join(PROVIDERS)}")


def words_from_characters(alignment: dict) -> list[dict]:
    """ElevenLabs gives per-character times; rebuild words from them."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words: list[dict] = []
    current, start, end = "", 0.0, 0.0
    for ch, s, e in zip(chars, starts, ends, strict=False):
        if ch.isspace():
            if current:
                words.append({"word": current, "start": round(start, 3), "end": round(end, 3)})
                current = ""
            continue
        if not current:
            start = s
        current += ch
        end = e
    if current:
        words.append({"word": current, "start": round(start, 3), "end": round(end, 3)})
    return words


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split long scripts at paragraph, then sentence boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    pieces = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if current and len(current) + len(piece) + 1 > limit:
            chunks.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks


def synthesize(voice: Voice, text: str, work_dir: Path) -> dict:
    """Speak the whole script, possibly in chunks, into one audio file with one word timeline."""
    work_dir.mkdir(parents=True, exist_ok=True)
    parts, words, offset = [], [], 0.0
    for i, chunk in enumerate(chunk_text(text)):
        speech = voice.speak(chunk)
        part = work_dir / f"voice-{i:02d}.mp3"
        part.write_bytes(speech.audio)
        duration = probe_duration(part)
        words += [
            {**w, "start": round(w["start"] + offset, 3), "end": round(w["end"] + offset, 3)}
            for w in speech.words
        ]
        parts.append(part)
        offset += duration
    output = work_dir / "voice.m4a"
    inputs = [arg for p in parts for arg in ("-i", str(p))]
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            "".join(f"[{i}:a]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]",
            "-map",
            "[a]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output),
        ]
    )
    for part in parts:
        part.unlink(missing_ok=True)
    duration = probe_duration(output)
    spoken = len(text.split())
    return {
        "audio_path": str(output),
        "duration_seconds": round(duration, 3),
        "words": words,
        "wpm": round(spoken / max(duration / 60, 1e-6), 1),
    }

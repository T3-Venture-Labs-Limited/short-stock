"""Small ffmpeg/ffprobe helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed ({exc.returncode}): {(exc.stderr or '').strip()[-1500:]}") from exc


def probe(path: Path) -> tuple[int, int, float]:
    """Return (width, height, duration_seconds); width/height are 0 without a video stream."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    duration = float(payload.get("format", {}).get("duration") or 0.0)
    return int(stream.get("width") or 0), int(stream.get("height") or 0), duration


def has_audio(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip() or 0.0)

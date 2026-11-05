"""Small ffmpeg/ffprobe helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

# ── finding ffmpeg ───────────────────────────────────────────────────────────

OVERRIDE_ENV = "SHORTSTOCK_FFMPEG"
# Homebrew's standard ffmpeg is built without libass, so it cannot draw captions. Its
# ffmpeg-full formula can, but is "keg-only": installed here, not on the PATH.
HOMEBREW_DIRS = ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin")


@dataclass(frozen=True, slots=True)
class FFmpeg:
    ffmpeg: str | None
    ffprobe: str | None
    libass: bool  # can draw captions


def _candidates() -> list[str]:
    found: list[str] = []
    override = os.environ.get(OVERRIDE_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        found.append((shutil.which("ffmpeg", path=str(path)) or "") if path.is_dir() else str(path))
    found.append(shutil.which("ffmpeg") or "")
    prefix = os.environ.get("HOMEBREW_PREFIX")
    for folder in ([f"{prefix}/opt/ffmpeg-full/bin"] if prefix else []) + list(HOMEBREW_DIRS):
        found.append(shutil.which("ffmpeg", path=folder) or "")
    return [c for c in dict.fromkeys(found) if c and os.access(c, os.X_OK)]


def _has_libass(binary: str) -> bool:
    try:
        out = subprocess.run([binary, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return " ass " in out.stdout


@cache
def find_ffmpeg() -> FFmpeg:
    """The ffmpeg to use: the first one that can draw captions, else any ffmpeg found."""
    candidates = _candidates()
    chosen = next((c for c in candidates if _has_libass(c)), None)
    libass = chosen is not None
    chosen = chosen or (candidates[0] if candidates else None)
    probe = None
    if chosen:
        probe = shutil.which("ffprobe", path=str(Path(chosen).parent)) or shutil.which("ffprobe")
    return FFmpeg(chosen, probe, libass)


def ffmpeg_bin() -> str:
    return find_ffmpeg().ffmpeg or "ffmpeg"


def ffprobe_bin() -> str:
    return find_ffmpeg().ffprobe or "ffprobe"


def install_hint() -> str:
    """How to get an ffmpeg that can draw captions on this system."""
    if sys.platform == "darwin":
        return "Run `brew install ffmpeg-full`, then restart shortstock; it is found automatically"
    if sys.platform.startswith("linux"):
        return f"Install your distribution's ffmpeg package (it includes libass), or set {OVERRIDE_ENV}"
    return f"Install an ffmpeg build that includes libass and set {OVERRIDE_ENV} to it"


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed ({exc.returncode}): {(exc.stderr or '').strip()[-1500:]}") from exc


def probe(path: Path) -> tuple[int, int, float]:
    """Return (width, height, duration_seconds); width/height are 0 without a video stream."""
    result = subprocess.run(
        [
            ffprobe_bin(),
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
            ffprobe_bin(),
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
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip() or 0.0)

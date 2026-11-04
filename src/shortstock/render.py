"""Assemble the video: stock shots cut to the narration, optional music, burned-in captions."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from shortstock.captions import ass_filter, write_ass
from shortstock.media import probe, run_ffmpeg

FPS = 30
SIZES = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}


def render_video(
    shots: list[dict],
    voice: dict,
    work_dir: Path,
    output: Path,
    aspect: str,
    caption_style: str | None,
    music_path: str | None = None,
    music_volume: float = 0.15,
) -> dict:
    width, height = SIZES[aspect]
    seg_dir = work_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for shot in shots:
        segment = seg_dir / f"{shot['index']:04d}.mp4"
        run_ffmpeg(
            [
                "-stream_loop",
                "-1",
                "-i",
                shot["clip_path"],
                "-t",
                f"{shot['duration']:.3f}",
                "-vf",
                fill_filter(width, height),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                str(segment),
            ]
        )
        segments.append(segment)

    concat_list = seg_dir / "list.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in segments), encoding="utf-8")
    silent = work_dir / "silent.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent)])

    duration = voice["duration_seconds"]
    inputs = ["-i", str(silent), "-i", voice["audio_path"]]
    filters: list[str] = []
    if caption_style and voice["words"]:
        # Landscape video: captions sit lower and slightly larger relative to the frame height.
        overrides = {"position": 0.1, "size": 0.065} if width > height else {}
        ass = write_ass(voice["words"], work_dir / "captions.ass", width, height, caption_style, **overrides)
        filters.append(f"[0:v]{ass_filter(ass)}[v]")
    else:
        filters.append("[0:v]null[v]")
    if music_path:
        inputs += ["-stream_loop", "-1", "-i", music_path]
        fade_at = max(0.0, duration - 2.0)
        filters += [
            "[1:a]asplit=2[vo][key]",
            f"[2:a]volume={music_volume},afade=t=out:st={fade_at:.2f}:d=2[bed]",
            # Duck the music under the voice.
            "[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[ducked]",
            "[vo][ducked]amix=inputs=2:duration=first:normalize=0[a]",
        ]
    else:
        filters.append("[1:a]anull[a]")

    output.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{duration + 0.3:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    make_poster(output, min(1.0, duration / 2))
    shutil.rmtree(seg_dir, ignore_errors=True)
    silent.unlink(missing_ok=True)
    out_w, out_h, out_duration = probe(output)
    return {
        "file_path": str(output),
        "width": out_w,
        "height": out_h,
        "duration_seconds": round(out_duration, 2),
    }


def fill_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
        f"setsar=1,fps={FPS},format=yuv420p"
    )


def poster_path(video: Path) -> Path:
    return video.with_suffix(".jpg")


def make_poster(video: Path, at: float) -> None:
    run_ffmpeg(
        [
            "-ss",
            str(at),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=540:-2",
            "-q:v",
            "4",
            str(poster_path(video)),
        ]
    )


def slugify(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return slug[:limit].rstrip("-") or "video"

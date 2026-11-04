"""Render with synthetic stock clips, voice and music (ffmpeg only, no network)."""

import shutil

import pytest

from shortstock.media import probe, run_ffmpeg
from shortstock.plan import align_sentences, build_shots, write_queries
from shortstock.render import render_video
from shortstock.script import parse_script

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


@pytest.mark.parametrize("aspect,size,music", [("9:16", (1080, 1920), False), ("16:9", (1920, 1080), True)])
def test_render(tmp_path, script, words, aspect, size, music):
    stock = tmp_path / "stock.mp4"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30:duration=2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(stock),
        ]
    )  # shorter than the shots: must loop
    voice_path = tmp_path / "voice.m4a"
    total = words[-1]["end"] + 0.2
    run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=300:duration={total}", "-c:a", "aac", str(voice_path)])
    music_path = None
    if music:
        music_path = tmp_path / "music.mp3"
        run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=500:duration=3", str(music_path)])

    sentences = write_queries(align_sentences(parse_script(script)["sentences"], words))
    shots = build_shots(sentences, 3.5, total)
    for shot in shots:
        shot["clip_path"] = str(stock)
    voice = {"audio_path": str(voice_path), "duration_seconds": total, "words": words}
    out = tmp_path / "out" / "video.mp4"

    result = render_video(
        shots, voice, tmp_path / "work", out, aspect, "bold", music_path and str(music_path)
    )

    width, height, duration = probe(out)
    assert (width, height) == size == (result["width"], result["height"])
    assert abs(duration - total) < 0.6
    assert out.with_suffix(".jpg").exists()

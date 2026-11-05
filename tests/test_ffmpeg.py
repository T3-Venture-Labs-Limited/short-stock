from pathlib import Path

from shortstock import media


def _fake_ffmpeg(folder: Path, libass: bool) -> Path:
    folder.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        tool = folder / name
        listing = " .. ass   V->V   Render ASS subtitles" if libass else " .. scale  V->V  Scale"
        tool.write_text(f"#!/bin/sh\necho '{listing}'\n")
        tool.chmod(0o755)
    return folder / "ffmpeg"


def test_find_ffmpeg_prefers_a_build_that_can_draw_captions(tmp_path: Path, monkeypatch):
    plain = _fake_ffmpeg(tmp_path / "usr-bin", libass=False)  # like Homebrew's standard ffmpeg
    full = _fake_ffmpeg(tmp_path / "ffmpeg-full", libass=True)  # like Homebrew's keg-only ffmpeg-full
    monkeypatch.setenv("PATH", str(plain.parent))
    monkeypatch.delenv("SHORTSTOCK_FFMPEG", raising=False)
    monkeypatch.delenv("HOMEBREW_PREFIX", raising=False)
    monkeypatch.setattr(media, "HOMEBREW_DIRS", (str(full.parent),))
    media.find_ffmpeg.cache_clear()
    try:
        found = media.find_ffmpeg()
        assert (found.ffmpeg, found.ffprobe, found.libass) == (str(full), str(full.parent / "ffprobe"), True)

        monkeypatch.setattr(media, "HOMEBREW_DIRS", ())
        media.find_ffmpeg.cache_clear()
        found = media.find_ffmpeg()
        assert found.ffmpeg == str(plain) and found.libass is False
        assert "ffmpeg" in media.install_hint()

        monkeypatch.setenv("SHORTSTOCK_FFMPEG", str(full.parent))
        media.find_ffmpeg.cache_clear()
        assert media.find_ffmpeg().ffmpeg == str(full)
    finally:
        media.find_ffmpeg.cache_clear()

"""Word-by-word animated captions, written as ASS subtitles and burned in by ffmpeg/libass."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from shortstock.config import PACKAGE_DIR

FONTS_DIR = PACKAGE_DIR / "fonts"


@dataclass(frozen=True, slots=True)
class CaptionStyle:
    font: str = "Archivo Black"
    size: float = 0.055  # fraction of video height
    case: str = "lower"  # lower | upper | none
    color: str = "FFFFFF"  # spoken word, RGB hex
    dim_alpha: int = 0x73  # transparency of words not being spoken (0 = opaque, 255 = invisible)
    emphasis_color: str | None = "FFD400"  # None disables the emphasis word
    emphasis_scale: float = 1.2
    outline: float = 0.0025  # fraction of height
    shadow: float = 0.0012
    position: float = 0.22  # distance from the bottom, fraction of height
    max_words: int = 3
    max_chars: int = 18


STYLES: dict[str, CaptionStyle] = {
    "bold": CaptionStyle(),
    "highlight": CaptionStyle(
        case="upper",
        dim_alpha=0x00,
        color="2BE36F",
        emphasis_color=None,
        size=0.05,
        max_words=3,
    ),
    "minimal": CaptionStyle(
        size=0.042,
        case="none",
        dim_alpha=0x00,
        color="FFFFFF",
        emphasis_color=None,
        max_words=5,
        max_chars=28,
        position=0.12,
    ),
}

EMPHASIS_STOP_WORDS = frozenset(
    """a an the is are was were be and or but not no in on at to of for by with from as it its this
    that he she we they his her my your our their i you me us him them do does did has have had
    will would could should can so if then just very too also more all about when who how what
    which""".split()
)


def clip_words(transcript: dict, start: float, end: float) -> list[dict]:
    """Words inside [start, end], re-timed so the clip starts at zero."""
    return [
        {
            "word": w["word"],
            "start": max(0.0, round(w["start"] - start, 3)),
            "end": max(0.0, round(min(w["end"], end) - start, 3)),
        }
        for w in transcript.get("words", [])
        if w["end"] > start and w["start"] < end
    ]


def chunk_words(words: list[dict], style: CaptionStyle) -> list[list[dict]]:
    """Group words into short single-line chunks, breaking early on sentence ends."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        text = " ".join(w["word"] for w in [*current, word])
        if current and (len(current) >= style.max_words or len(text) > style.max_chars):
            chunks.append(current)
            current = []
        current.append(word)
        if word["word"].endswith((".", "!", "?")):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def emphasis_index(chunk: list[dict]) -> int | None:
    candidates = [
        (i, _display(w["word"], "lower"))
        for i, w in enumerate(chunk)
        if _display(w["word"], "lower") not in EMPHASIS_STOP_WORDS
    ]
    if not candidates:
        return None
    index, word = max(candidates, key=lambda c: len(c[1]))
    return index if len(word) >= 5 else None


def write_ass(words: list[dict], path: Path, width: int, height: int, style_name: str, **overrides) -> Path:
    style = replace(STYLES.get(style_name, STYLES["bold"]), **overrides)
    font_size = round(height * style.size)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style.font},{font_size},{_ass_color(style.color)},&H000000FF,"
        f"&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,{round(height * style.outline, 1)},"
        f"{round(height * style.shadow, 1)},2,{round(width * 0.08)},{round(width * 0.08)},"
        f"{round(height * style.position)},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    chunks = chunk_words(words, style)
    for n, chunk in enumerate(chunks):
        chunk_end = chunk[-1]["end"] + 0.25
        if n + 1 < len(chunks):
            chunk_end = min(chunk_end, chunks[n + 1][0]["start"])
        emphasis = emphasis_index(chunk) if style.emphasis_color else None
        for i, word in enumerate(chunk):
            start = word["start"]
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else chunk_end
            if end - start < 0.02:
                continue
            parts = []
            for j, other in enumerate(chunk):
                tags = []
                if j == emphasis and style.emphasis_color:
                    tags.append(f"\\c{_ass_color(style.emphasis_color)}")
                    if style.emphasis_scale != 1.0:
                        tags.append(f"\\fs{round(font_size * style.emphasis_scale)}")
                elif j == i:
                    tags.append(f"\\c{_ass_color(style.color)}")
                else:
                    tags.append("\\c&HFFFFFF&")
                tags.append(f"\\alpha&H{0 if j == i else style.dim_alpha:02X}&")
                parts.append("{" + "".join(tags) + "}" + _escape(_display(other["word"], style.case)))
            fade = "{\\fad(120,0)}" if i == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{fade}{' '.join(parts)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ass_filter(path: Path) -> str:
    return f"ass={_filter_path(path)}:fontsdir={_filter_path(FONTS_DIR)}"


def _display(word: str, case: str) -> str:
    text = word.strip().rstrip(",.;:") if not word.endswith("...") else word.strip()
    return text.lower() if case == "lower" else text.upper() if case == "upper" else text


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _ass_color(rgb: str) -> str:
    rgb = rgb.lstrip("#")
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&".upper()


def _ts(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    h, rem = divmod(centis, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

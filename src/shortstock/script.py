"""Parse the user's script into narration text and sentences with footage directions.

Directions live in the script itself, so the script stays the single source of truth for the
web app, the CLI and agents:

- ``[visual: city skyline at night]`` sets the footage search for its sentence.
- ``[clip: 123456]`` locks a specific Pexels video for its sentence.

A direction on its own line applies to the next sentence. Markdown headings are not read
aloud; the first one becomes the default title. Other ``[bracketed]`` text is not spoken.
"""

from __future__ import annotations

import re

HINT = re.compile(r"\[\s*(?:visual|footage|broll|b-roll)\s*:\s*([^\]]*)\]", re.IGNORECASE)
CLIP = re.compile(r"\[\s*clip\s*:\s*(?:pexels\s*)?(\d+)\s*\]", re.IGNORECASE)
DIRECTION = re.compile(r"\[[^\]]*\]|\{[^}]*\}")
LIST_PREFIX = re.compile(r"^\s{0,3}(?:>\s?|[-*+]\s+|\d+[.)]\s+)")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
SENTENCE_END = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")


def parse_script(script: str) -> dict:
    """Return the text to speak and its sentences.

    Each sentence carries its footage ``hint`` and ``pin`` (a Pexels id), plus character offsets
    into ``script`` so editors can insert or replace directions: ``start``/``end`` cover the
    sentence, ``hint_span``/``pin_span`` cover the directions that apply to it.
    """
    if not script.strip():
        raise ValueError("The script is empty")
    sentences: list[dict] = []
    title: str | None = None
    pending: dict = {}
    for line in re.finditer(r"[^\n]+", script):
        heading = HEADING.match(line.group())
        if heading:
            title = title or heading.group(1).strip()
            continue
        prefix = LIST_PREFIX.match(line.group())
        offset = line.start() + (prefix.end() if prefix else 0)
        content = line.group()[prefix.end() if prefix else 0 :]
        for seg_start, seg_end in _segments(content):
            raw = content[seg_start:seg_end]
            for match in HINT.finditer(raw):
                pending["hint"] = (
                    match.group(1).strip(),
                    (offset + seg_start + match.start(), offset + seg_start + match.end()),
                )
            for match in CLIP.finditer(raw):
                pending["pin"] = (
                    int(match.group(1)),
                    (offset + seg_start + match.start(), offset + seg_start + match.end()),
                )
            text = _clean(raw)
            if not text:
                continue
            hint, hint_span = pending.get("hint", (None, None))
            pin, pin_span = pending.get("pin", (None, None))
            sentences.append(
                {
                    "text": text,
                    "hint": hint or None,
                    "pin": pin,
                    "start": offset + seg_start,
                    "end": offset + seg_end,
                    "hint_span": hint_span,
                    "pin_span": pin_span,
                }
            )
            pending = {}
    if not sentences:
        raise ValueError("The script has no spoken text")
    return {"text": " ".join(s["text"] for s in sentences), "sentences": sentences, "title": title}


def _segments(content: str) -> list[tuple[int, int]]:
    """Sentence spans within one line, keeping leading directions with their sentence."""
    spans, start = [], 0
    for match in SENTENCE_END.finditer(content):
        spans.append((start, match.start()))
        start = match.end()
    if start < len(content):
        spans.append((start, len(content)))
    return [(s, e) for s, e in spans if content[s:e].strip()]


def _clean(raw: str) -> str:
    text = DIRECTION.sub("", raw)
    text = re.sub(r"[*_`]{1,3}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?…])", r"\1", text)


def normalise(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())

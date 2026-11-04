"""Turn the timed narration into shots: one footage search per sentence, cut on word timings."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from shortstock.script import normalise

logger = logging.getLogger(__name__)

MIN_SHOT = 1.2

STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would could should may might "
    "shall can i you he she it we they me him her us them my your his its our their this that these those "
    "and or but if then so because as of in on at to for with from by about into over after before up down "
    "out off not no yes just very really also too more most some any all what which who whom whose when "
    "where why how there here than like get got go going know think mean thing things something anything "
    "everything one two well right okay yeah actually basically literally people want said say says see "
    "let lets dont doesnt didnt cant wont im youre thats theres".split()
)

QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "query": {"type": "string"}},
                "required": ["index", "query"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["queries"],
    "additionalProperties": False,
}

QUERY_PROMPT = (
    "You choose stock footage for a narrated short video. For each numbered sentence, write one "
    "search query for a stock video site such as Pexels: 2 to 5 concrete, filmable English words "
    "describing what should be on screen (for example 'city skyline at night', 'hands typing on "
    "laptop', 'runner on mountain trail'). Show the idea visually; avoid abstract words, text, logos, "
    "brand names and named people. Vary the shots so consecutive sentences look different. Return JSON."
)


def align_sentences(sentences: list[dict], words: list[dict]) -> list[dict]:
    """Give each sentence a start and end time by matching its words to the spoken words."""
    script_tokens: list[str] = []
    owner: list[int] = []
    for i, sentence in enumerate(sentences):
        for token in sentence["text"].split():
            script_tokens.append(normalise(token))
            owner.append(i)
    spoken = [normalise(w["word"]) for w in words]
    mapping: dict[int, int] = {}
    for block in SequenceMatcher(None, script_tokens, spoken, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            mapping[block.a + k] = block.b + k
    total = words[-1]["end"] if words else 0.0

    timed = []
    for i, sentence in enumerate(sentences):
        indexes = [mapping[t] for t, o in enumerate(owner) if o == i and t in mapping]
        if indexes:
            start, end = words[min(indexes)]["start"], words[max(indexes)]["end"]
        else:  # no word matched: place it proportionally by token position
            first = owner.index(i) / max(1, len(owner))
            last = (len(owner) - owner[::-1].index(i)) / max(1, len(owner))
            start, end = first * total, last * total
        timed.append({**sentence, "start": round(start, 3), "end": round(end, 3)})

    # Cut halfway through the pause between sentences, so the picture never goes black.
    bounds = [0.0]
    for i in range(len(timed) - 1):
        cut = (timed[i]["end"] + timed[i + 1]["start"]) / 2
        bounds.append(round(max(bounds[-1], cut), 3))
    bounds.append(max(bounds[-1], timed[-1]["end"]) if timed else 0.0)
    for i, sentence in enumerate(timed):
        sentence["start"], sentence["end"] = bounds[i], bounds[i + 1]
    return timed


def match_ratio(text: str, words: list[dict]) -> float:
    """Share of script words that the provider returned timings for, in order."""
    script_tokens = [normalise(t) for t in text.split()]
    spoken = [normalise(w["word"]) for w in words]
    matcher = SequenceMatcher(None, script_tokens, spoken, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return round(matched / max(1, len(script_tokens)), 3)


def write_queries(sentences: list[dict], llm=None) -> list[dict]:
    """Fill in footage searches: the user's hint, else the AI, else keywords from the sentence."""
    missing = [i for i, s in enumerate(sentences) if not s.get("hint")]
    ai: dict[int, str] = {}
    if missing and llm is not None:
        numbered = "\n".join(f"{i}. {sentences[i]['text']}" for i in missing)
        try:
            data = llm.complete_json(QUERY_PROMPT, numbered, QUERY_SCHEMA, "footage_queries")
            ai = {int(q["index"]): str(q["query"]).strip() for q in data.get("queries", []) if q.get("query")}
        except Exception as exc:  # the AI is optional; keywords still work
            logger.warning("AI footage queries failed, using keywords: %s", exc)
    result = []
    for i, sentence in enumerate(sentences):
        query = (
            sentence.get("hint") or ai.get(i) or " ".join(keywords(sentence["text"])) or "abstract background"
        )
        source = "hint" if sentence.get("hint") else "ai" if i in ai else "keywords"
        result.append({**sentence, "query": query, "query_source": source})
    return result


def build_shots(sentences: list[dict], max_shot: float, total: float) -> list[dict]:
    """Split each sentence's time into shots no longer than ``max_shot`` seconds."""
    shots = []
    for i, sentence in enumerate(sentences):
        start = sentence["start"]
        end = total if i == len(sentences) - 1 else sentence["end"]
        duration = end - start
        if duration <= 0:
            continue
        count = max(1, round(duration / max_shot + 0.49)) if duration > max_shot else 1
        while count > 1 and duration / count < MIN_SHOT:
            count -= 1
        for k in range(count):
            shot_start = start + duration * k / count
            shot_end = start + duration * (k + 1) / count
            shots.append(
                {
                    "index": len(shots),
                    "sentence": i,
                    "start": round(shot_start, 3),
                    "end": round(shot_end, 3),
                    "duration": round(shot_end - shot_start, 3),
                    "query": sentence["query"],
                    "text": sentence["text"],
                    "pin": sentence.get("pin") if k == 0 else None,
                }
            )
    return shots


def keywords(text: str, limit: int = 3) -> list[str]:
    seen: list[str] = []
    for word in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower()):
        if len(word) > 3 and word.replace("'", "") not in STOP_WORDS and word not in seen:
            seen.append(word)
    return sorted(seen, key=len, reverse=True)[:limit]

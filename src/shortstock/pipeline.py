"""The shortstock pipeline: a list of resumable stages.

Each stage writes ``<run>/work/<stage>.json``. If that file exists the stage is skipped on a
retry, so a failed run resumes where it stopped instead of paying for the voiceover again.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from shortstock import db
from shortstock.config import get_setting, runs_dir

logger = logging.getLogger(__name__)

MIN_TIMED_RATIO = 0.9


class VideoOptions(BaseModel):
    voice_provider: Literal["elevenlabs", "fish"] | None = Field(None, description="Default from settings")
    voice_id: str | None = Field(None, description="Default from settings")
    speed: float = Field(1.0, ge=0.7, le=1.2)
    aspect_ratio: Literal["9:16", "4:5", "1:1", "16:9"] = "9:16"
    captions: bool = True
    caption_style: Literal["bold", "highlight", "minimal"] = "bold"
    max_shot_seconds: float = Field(3.5, ge=1.5, le=10)
    music: str | None = Field(None, description="Path to a music file played under the voice")
    music_volume: float = Field(0.15, ge=0.0, le=1.0)
    caption: str = Field("", max_length=2200, description="Post caption, for publishing")
    hashtags: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class Context:
    run_id: str
    script: str
    title: str
    options: dict[str, Any]
    work_dir: Path
    out_dir: Path
    state: dict[str, Any]


def run_dir(run_id: str) -> Path:
    return runs_dir() / run_id


# ── stages ───────────────────────────────────────────────────────────────────


def stage_voice(ctx: Context) -> dict:
    from shortstock.plan import match_ratio
    from shortstock.script import parse_script
    from shortstock.tts import get_voice, synthesize

    parsed = parse_script(ctx.script)
    voice = get_voice(ctx.options["voice_provider"], ctx.options["voice_id"], ctx.options["speed"])
    result = synthesize(voice, parsed["text"], ctx.work_dir)
    result["timed_ratio"] = match_ratio(parsed["text"], result["words"])
    if result["timed_ratio"] < MIN_TIMED_RATIO:
        raise RuntimeError(
            f"The voice provider timed only {result['timed_ratio']:.0%} of the words, so captions and cuts "
            "would drift. Try again or use another voice."
        )
    return {**result, "sentences": parsed["sentences"], "provider": type(voice).__name__}


def stage_plan(ctx: Context) -> dict:
    from shortstock.plan import align_sentences, build_shots, write_queries

    voice = ctx.state["voice"]
    sentences = align_sentences(voice["sentences"], voice["words"])
    llm = None
    if get_setting("openrouter_api_key") and any(not s.get("hint") for s in sentences):
        from shortstock.llm import get_llm

        llm = get_llm()
    sentences = write_queries(sentences, llm)
    shots = build_shots(sentences, ctx.options["max_shot_seconds"], voice["duration_seconds"])
    return {"sentences": sentences, "shots": shots}


def stage_footage(ctx: Context) -> dict:
    from shortstock.footage import fill_shots
    from shortstock.render import SIZES

    shots = json.loads(json.dumps(ctx.state["plan"]["shots"]))
    width = min(SIZES[ctx.options["aspect_ratio"]])
    avoid_file = ctx.work_dir / "used_clips.json"
    avoid = set(json.loads(avoid_file.read_text())) if avoid_file.exists() else set()
    return fill_shots(shots, get_setting("pexels_api_key"), ctx.options["aspect_ratio"], width, avoid=avoid)


def stage_render(ctx: Context) -> dict:
    from shortstock.render import render_video, slugify

    output = ctx.out_dir / f"{slugify(ctx.title)}.mp4"
    result = render_video(
        ctx.state["footage"]["shots"],
        ctx.state["voice"],
        ctx.work_dir,
        output,
        ctx.options["aspect_ratio"],
        ctx.options["caption_style"] if ctx.options["captions"] else None,
        ctx.options["music"],
        ctx.options["music_volume"],
    )
    db.save_video(
        ctx.run_id,
        title=ctx.title,
        caption=ctx.options["caption"],
        hashtags=ctx.options["hashtags"],
        **result,
    )
    return result


STAGES: list[tuple[str, str, Callable[[Context], dict]]] = [
    ("voice", "Voiceover", stage_voice),
    ("plan", "Plan shots", stage_plan),
    ("footage", "Find footage", stage_footage),
    ("render", "Render", stage_render),
]
STAGE_NAMES = [name for name, _, _ in STAGES]


# ── runner ───────────────────────────────────────────────────────────────────


def default_title(script: str) -> str:
    from shortstock.script import parse_script

    try:
        parsed = parse_script(script)
    except ValueError:
        return "Untitled"
    if parsed["title"]:
        return parsed["title"]
    first = parsed["sentences"][0]["text"]
    return first if len(first) <= 70 else first[:67].rsplit(" ", 1)[0] + "…"


def execute(run: dict[str, Any], on_stage: Callable[[str], None] | None = None) -> None:
    """Run (or resume) every stage for a claimed run. Marks the run completed or failed."""
    run_id = run["id"]
    ctx = Context(
        run_id=run_id,
        script=run["script"],
        title=run["title"] or default_title(run["script"]),
        options=VideoOptions(**run["options"]).model_dump(),
        work_dir=run_dir(run_id) / "work",
        out_dir=run_dir(run_id) / "output",
        state={},
    )
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    for name, _, fn in STAGES:
        artifact = ctx.work_dir / f"{name}.json"
        if artifact.exists():
            ctx.state[name] = json.loads(artifact.read_text(encoding="utf-8"))
            db.set_stage(run_id, name, "done")
            continue
        db.update_run(run_id, current_stage=name)
        db.set_stage(run_id, name, "running")
        if on_stage:
            on_stage(name)
        try:
            result = fn(ctx)
        except Exception as exc:
            logger.exception("run %s failed in %s", run_id, name)
            db.set_stage(run_id, name, "failed", str(exc))
            db.update_run(run_id, status="failed", error=f"{name}: {exc}")
            return
        tmp = artifact.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(artifact)
        ctx.state[name] = result
        db.set_stage(run_id, name, "done")
    db.update_run(run_id, status="completed", current_stage=None, error=None, title=ctx.title)


def retry(run_id: str, from_stage: str | None = None) -> None:
    """Queue a run again. With ``from_stage`` that stage and every later one are redone."""
    if from_stage:
        work = run_dir(run_id) / "work"
        _remember_clips(work)
        for name in STAGE_NAMES[STAGE_NAMES.index(from_stage) :]:
            (work / f"{name}.json").unlink(missing_ok=True)
            db.set_stage(run_id, name, "pending")
    db.update_run(run_id, status="queued", error=None)


def _remember_clips(work: Path) -> None:
    """Keep the ids of clips already cut in, so asking for new footage gets different clips."""
    footage = work / "footage.json"
    if not footage.exists():
        return
    avoid_file = work / "used_clips.json"
    used = set(json.loads(avoid_file.read_text())) if avoid_file.exists() else set()
    pinned = {s.get("pin") for s in json.loads(footage.read_text())["shots"]}
    used |= {s["clip_id"] for s in json.loads(footage.read_text())["shots"] if s.get("clip_id") not in pinned}
    avoid_file.write_text(json.dumps(sorted(used)))


def delete(run_id: str) -> None:
    db.delete_run(run_id)
    shutil.rmtree(run_dir(run_id), ignore_errors=True)


def run_next() -> str | None:
    run = db.claim_next_run()
    if run is None:
        return None
    execute(run)
    return run["id"]

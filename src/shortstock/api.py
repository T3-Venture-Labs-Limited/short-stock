"""HTTP API and web UI."""

from __future__ import annotations

import json
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shortstock import __version__, db, pipeline
from shortstock.config import PACKAGE_DIR, SETTINGS, get_setting, mask, uploads_dir
from shortstock.doctor import checks
from shortstock.publish import BufferClient, PublishError, PublishMode, publish_video
from shortstock.worker import Worker

WEB_DIR = PACKAGE_DIR / "web"


class CreateRun(BaseModel):
    script: str = Field(..., min_length=1, max_length=60_000)
    title: str | None = Field(None, max_length=200)
    options: pipeline.VideoOptions = pipeline.VideoOptions()


class ScriptBody(BaseModel):
    script: str = Field(..., max_length=60_000)


class RetryRun(BaseModel):
    from_stage: str | None = None


class UpdateSettings(BaseModel):
    values: dict[str, str | None]


class PublishRequest(BaseModel):
    channel_ids: list[str] = Field(..., min_length=1)
    mode: PublishMode = "queue"
    scheduled_at: datetime | None = None
    text: str | None = None
    title: str | None = None


def create_app(start_worker: bool = True) -> FastAPI:
    worker = Worker() if start_worker else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="shortstock", version=__version__, lifespan=lifespan)

    # ── health & settings ────────────────────────────────────────────────────

    @app.get("/api/health")
    def health() -> dict:
        return {
            "version": __version__,
            "checks": checks(),
            "queue": db.queue_counts(),
            "worker": bool(worker),
        }

    @app.get("/api/settings")
    def get_settings() -> list[dict]:
        result = []
        for key, spec in SETTINGS.items():
            stored = db.get_setting(key)
            value = get_setting(key)
            source = "app" if stored else "env" if os.environ.get(spec.env) else "default"
            result.append(
                {
                    "key": key,
                    "value": mask(value) if spec.secret else value,
                    "is_set": bool(value),
                    "secret": spec.secret,
                    "source": source,
                    "env": spec.env,
                    "description": spec.description,
                }
            )
        return result

    @app.put("/api/settings")
    def put_settings(body: UpdateSettings) -> list[dict]:
        for key, value in body.values.items():
            if key not in SETTINGS:
                raise HTTPException(400, f"Unknown setting: {key}")
            if SETTINGS[key].secret and value and "••••" in value:
                continue  # unchanged masked value sent back by the UI
            db.set_setting(key, value.strip() if value else None)
        return get_settings()

    @app.get("/api/models")
    def models() -> list[dict]:
        from shortstock.llm import list_models

        try:
            return list_models()
        except Exception as exc:
            raise HTTPException(502, f"Could not load models: {exc}") from exc

    @app.get("/api/voices")
    def voices(provider: str | None = None, search: str = "", current: str | None = None) -> list[dict]:
        from shortstock.tts import Fish, TTSError, get_voice

        try:
            voice = get_voice(provider, voice_id="list")
            return voice.voices(search, current) if isinstance(voice, Fish) else voice.voices()
        except TTSError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ── storyboard (before anything is paid for) ─────────────────────────────

    @app.post("/api/storyboard")
    def storyboard(body: ScriptBody) -> dict:
        from shortstock.plan import keywords
        from shortstock.script import parse_script

        try:
            parsed = parse_script(body.script)
        except ValueError:
            return {"title": None, "sentences": [], "words": 0}
        sentences = []
        for i, s in enumerate(parsed["sentences"]):
            query = s["hint"] or " ".join(keywords(s["text"])) or "abstract background"
            sentences.append(
                {**s, "index": i, "query": query, "query_source": "hint" if s["hint"] else "keywords"}
            )
        return {"title": parsed["title"], "sentences": sentences, "words": len(parsed["text"].split())}

    @app.post("/api/storyboard/suggest")
    def suggest(body: ScriptBody) -> list[dict]:
        """Ask the AI for footage searches for sentences without a hint."""
        from shortstock.llm import LLMError, get_llm
        from shortstock.plan import write_queries
        from shortstock.script import parse_script

        if not get_setting("openrouter_api_key"):
            raise HTTPException(400, "Add an OpenRouter key in Settings to get AI footage suggestions")
        try:
            sentences = write_queries(parse_script(body.script)["sentences"], get_llm())
        except (ValueError, LLMError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return [
            {"index": i, "query": s["query"]} for i, s in enumerate(sentences) if s["query_source"] == "ai"
        ]

    @app.get("/api/footage/search")
    def footage_search(q: str, aspect: str = "9:16") -> list[dict]:
        from shortstock.footage import FootageError, orientation_for, search

        if aspect not in ("9:16", "4:5", "1:1", "16:9"):
            raise HTTPException(400, "Unknown aspect ratio")
        try:
            return search(q, orientation_for(aspect), get_setting("pexels_api_key"))[:8]
        except FootageError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/footage/{video_id}")
    def footage_item(video_id: int) -> dict:
        from shortstock.footage import FootageError, get_video

        try:
            return get_video(video_id, get_setting("pexels_api_key"))
        except FootageError as exc:
            raise HTTPException(404, str(exc)) from exc

    # ── runs ─────────────────────────────────────────────────────────────────

    @app.post("/api/uploads")
    def upload(file: UploadFile) -> dict:
        name = Path(file.filename or "upload").name
        target = uploads_dir() / f"{db.new_id()}-{name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fh:
            shutil.copyfileobj(file.file, fh, length=1024 * 1024)
        return {"path": str(target), "name": name}

    @app.post("/api/runs")
    def create_run(body: CreateRun) -> dict:
        run = db.create_run(body.script, body.options.model_dump(), title=(body.title or "").strip() or None)
        if worker:
            worker.wake()
        return run

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return db.list_runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        return run_detail(run_id)

    @app.post("/api/runs/{run_id}/retry")
    def retry_run(run_id: str, body: RetryRun | None = None) -> dict:
        run = _run_or_404(run_id)
        if run["status"] in {"queued", "running"}:
            raise HTTPException(409, "Run is already queued or running")
        from_stage = body.from_stage if body else None
        if from_stage and from_stage not in pipeline.STAGE_NAMES:
            raise HTTPException(400, f"Unknown stage: {from_stage}")
        pipeline.retry(run_id, from_stage)
        if worker:
            worker.wake()
        return run_detail(run_id)

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str) -> dict:
        run = _run_or_404(run_id)
        if run["status"] == "running":
            raise HTTPException(409, "Wait for the run to finish before deleting it")
        pipeline.delete(run_id)
        return {"deleted": run_id}

    # ── videos & publishing ──────────────────────────────────────────────────

    @app.get("/api/videos/{video_id}/file")
    def video_file(video_id: str, download: bool = False) -> FileResponse:
        path = _video_path(video_id)
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=path.name if download else None,
            content_disposition_type="attachment" if download else "inline",
        )

    @app.get("/api/videos/{video_id}/poster")
    def video_poster(video_id: str) -> FileResponse:
        from shortstock.render import make_poster, poster_path

        path = _video_path(video_id)
        poster = poster_path(path)
        if not poster.exists():
            make_poster(path, 1.0)
        return FileResponse(poster, media_type="image/jpeg")

    @app.get("/api/buffer/channels")
    def buffer_channels() -> list[dict]:
        try:
            return BufferClient().channels()
        except PublishError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/buffer/organizations")
    def buffer_organizations() -> list[dict]:
        try:
            return BufferClient().organizations()
        except PublishError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/videos/{video_id}/publish")
    def publish(video_id: str, body: PublishRequest) -> list[dict]:
        try:
            return publish_video(
                video_id, body.channel_ids, body.mode, body.scheduled_at, body.text, body.title
            )
        except PublishError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ── web UI ───────────────────────────────────────────────────────────────

    if (WEB_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (WEB_DIR / path).resolve()
            if path and candidate.is_file() and WEB_DIR.resolve() in candidate.parents:
                return FileResponse(candidate)
            # Always revalidate the page, so an upgrade never runs yesterday's scripts.
            return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def run_detail(run_id: str) -> dict:
    run = _run_or_404(run_id)
    stage_rows = {s["name"]: s for s in db.list_stages(run_id)}
    stages = []
    for name, label, _ in pipeline.STAGES:
        row = stage_rows.get(name, {})
        stages.append(
            {
                "name": name,
                "label": label,
                "status": row.get("status", "pending"),
                "error": row.get("error"),
                "started_at": row.get("started_at"),
                "finished_at": row.get("finished_at"),
            }
        )
    work = pipeline.run_dir(run_id) / "work"
    shots, credits = [], []
    footage = work / "footage.json"
    if footage.exists():
        data = json.loads(footage.read_text(encoding="utf-8"))
        credits = data.get("credits", [])
        shots = [
            {
                k: s.get(k)
                for k in (
                    "index",
                    "sentence",
                    "start",
                    "end",
                    "duration",
                    "query",
                    "text",
                    "clip_id",
                    "thumb",
                )
            }
            for s in data.get("shots", [])
        ]
    voice = work / "voice.json"
    voice_info = None
    if voice.exists():
        data = json.loads(voice.read_text(encoding="utf-8"))
        voice_info = {k: data.get(k) for k in ("duration_seconds", "timed_ratio", "wpm", "provider")}
    video = db.video_for_run(run_id)
    return {
        **run,
        "stages": stages,
        "video": _video_public(video) if video else None,
        "voice": voice_info,
        "shots": shots,
        "credits": credits,
        "posts": db.list_posts(run_id=run_id),
    }


def _video_public(video: dict) -> dict:
    data = {k: v for k, v in video.items() if k != "file_path"}
    data["filename"] = Path(video["file_path"]).name
    data["url"] = f"/api/videos/{video['id']}/file"
    data["download_url"] = f"/api/videos/{video['id']}/file?download=true"
    data["poster_url"] = f"/api/videos/{video['id']}/poster"
    return data


def _video_path(video_id: str) -> Path:
    video = db.get_video(video_id)
    if not video or not Path(video["file_path"]).exists():
        raise HTTPException(404, "Video not found")
    return Path(video["file_path"])


def _run_or_404(run_id: str) -> dict[str, Any]:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run

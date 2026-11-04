"""Command line interface. Every command that returns data supports --json for agents."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from shortstock import __version__


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # surface a clean message instead of a traceback
        if args.verbose:
            raise
        _fail(str(exc), getattr(args, "json", False))
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shortstock",
        description="Turn a script into a narrated stock-footage video. Web UI: `shortstock serve`.",
    )
    p.add_argument("--version", action="version", version=f"shortstock {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="show debug logs and tracebacks")
    sub = p.add_subparsers(metavar="command")

    s = sub.add_parser("serve", help="start the web UI and background worker")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-worker", action="store_true", help="do not process the queue")
    s.set_defaults(func=cmd_serve)

    m = sub.add_parser("make", help="make a video from a script file (or - for stdin)")
    m.add_argument("script", help="path to a text or Markdown script, or - to read stdin")
    m.add_argument("--title", help="video title (default: the first sentence)")
    m.add_argument(
        "--voice",
        help="provider:voice_id, e.g. elevenlabs:JBFqnCBsd6RMkjVDRZzb or fish:<id> (default: settings)",
    )
    m.add_argument("--speed", type=float, default=1.0, help="speech speed, 0.7 to 1.2")
    m.add_argument("--aspect", choices=["9:16", "4:5", "1:1", "16:9"], default="9:16")
    m.add_argument("--style", choices=["bold", "highlight", "minimal"], default="bold", help="caption style")
    m.add_argument("--no-captions", action="store_true")
    m.add_argument("--max-shot", type=float, default=3.5, help="longest shot in seconds (3.5)")
    m.add_argument("--music", type=Path, help="music file to play quietly under the voice")
    m.add_argument("--music-volume", type=float, default=0.15)
    m.add_argument("--caption", default="", help="post caption, used when publishing")
    m.add_argument("--hashtags", default="", help="space-separated hashtags, used when publishing")
    m.add_argument("-o", "--out", type=Path, help="copy the finished video into this folder")
    m.add_argument("--queue", action="store_true", help="only queue the run for a running `shortstock serve`")
    m.add_argument("--json", action="store_true", help="print machine-readable JSON")
    m.set_defaults(func=cmd_make)

    r = sub.add_parser("runs", help="list runs")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_runs)

    sh = sub.add_parser("show", help="show a run and its video")
    sh.add_argument("run_id")
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    rt = sub.add_parser("retry", help="resume a failed run, or redo it from a stage")
    rt.add_argument("run_id")
    rt.add_argument("--from", dest="from_stage", help="stage to redo from: voice, plan, footage, render")
    rt.add_argument("--json", action="store_true")
    rt.set_defaults(func=cmd_retry)

    d = sub.add_parser("delete", help="delete a run and its files")
    d.add_argument("run_id")
    d.set_defaults(func=cmd_delete)

    v = sub.add_parser("voices", help="list voices for a provider")
    v.add_argument("--provider", choices=["elevenlabs", "fish"], help="default: settings")
    v.add_argument("--search", default="", help="Fish Audio: search the public voice library")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_voices)

    f = sub.add_parser("footage", help="search Pexels footage, to choose clips for [clip: id]")
    f.add_argument("query")
    f.add_argument("--aspect", choices=["9:16", "4:5", "1:1", "16:9"], default="9:16")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_footage)

    cfg = sub.add_parser("config", help="view or change settings (API keys, voices)")
    cfg_sub = cfg.add_subparsers(metavar="action")
    cl = cfg_sub.add_parser("list", help="show all settings")
    cl.add_argument("--json", action="store_true")
    cl.set_defaults(func=cmd_config_list)
    cs = cfg_sub.add_parser("set", help="save a setting")
    cs.add_argument("key")
    cs.add_argument("value")
    cs.set_defaults(func=cmd_config_set)
    cu = cfg_sub.add_parser("unset", help="clear a saved setting")
    cu.add_argument("key")
    cu.set_defaults(func=cmd_config_unset)
    cfg.set_defaults(func=cmd_config_list, json=False)

    doc = sub.add_parser("doctor", help="check ffmpeg, keys and optional integrations")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=cmd_doctor)

    ch = sub.add_parser("channels", help="list your Buffer channels")
    ch.add_argument("--json", action="store_true")
    ch.set_defaults(func=cmd_channels)

    pb = sub.add_parser("publish", help="send a video to Buffer")
    pb.add_argument("video_id")
    pb.add_argument("--channel", action="append", required=True, dest="channels", help="Buffer channel id")
    pb.add_argument("--mode", choices=["queue", "now", "schedule", "draft"], default="queue")
    pb.add_argument("--at", help="ISO time for --mode schedule, e.g. 2026-11-05T18:00:00Z")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(func=cmd_publish)
    return p


# ── commands ─────────────────────────────────────────────────────────────────


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from shortstock.api import WEB_DIR, create_app

    if not (WEB_DIR / "index.html").exists():
        print(
            "Note: the web UI is not built; only the API is available. "
            "Run `npm --prefix frontend run build` from the repo.",
            file=sys.stderr,
        )
    print(f"shortstock {__version__} running at http://{args.host}:{args.port}", file=sys.stderr)
    logging.getLogger().setLevel(logging.INFO)
    uvicorn.run(
        create_app(start_worker=not args.no_worker), host=args.host, port=args.port, log_level="warning"
    )
    return 0


def cmd_make(args: argparse.Namespace) -> int:
    from shortstock import db, pipeline

    script = sys.stdin.read() if args.script == "-" else Path(args.script).expanduser().read_text("utf-8")
    provider, voice_id = None, None
    if args.voice:
        provider, _, voice_id = args.voice.partition(":")
        voice_id = voice_id or None
    options = pipeline.VideoOptions(
        voice_provider=provider or None,
        voice_id=voice_id,
        speed=args.speed,
        aspect_ratio=args.aspect,
        caption_style=args.style,
        captions=not args.no_captions,
        max_shot_seconds=args.max_shot,
        music=str(args.music.expanduser().resolve()) if args.music else None,
        music_volume=args.music_volume,
        caption=args.caption,
        hashtags=args.hashtags.split(),
    ).model_dump()

    if args.queue:
        run = db.create_run(script, options, title=args.title)
        _emit(args, {"run_id": run["id"], "status": "queued"}, f"Queued run {run['id']}")
        return 0

    run = db.create_run(script, options, title=args.title, status="running")
    _log(f"Run {run['id']}")
    pipeline.execute(run, on_stage=lambda name: _log(f"  {name}…"))
    return _report(args, run["id"])


def cmd_retry(args: argparse.Namespace) -> int:
    from shortstock import db, pipeline

    run = _require_run(args.run_id)
    if run["status"] == "running":
        raise RuntimeError("That run is still running")
    pipeline.retry(run["id"], args.from_stage)
    db.update_run(run["id"], status="running", claimed_by=os.getpid())
    pipeline.execute(db.get_run(run["id"]), on_stage=lambda name: _log(f"  {name}…"))
    return _report(args, run["id"])


def _report(args: argparse.Namespace, run_id: str) -> int:
    from shortstock import db
    from shortstock.api import run_detail

    detail = run_detail(run_id)
    video = detail["video"]
    file = None
    if video:
        file = db.get_video(video["id"])["file_path"]
        if getattr(args, "out", None):
            args.out.mkdir(parents=True, exist_ok=True)
            dest = args.out / Path(file).name
            shutil.copy2(file, dest)
            file = str(dest.resolve())
    payload = {
        "run_id": run_id,
        "status": detail["status"],
        "title": detail["title"],
        "error": detail["error"],
        "video": {
            "id": video["id"],
            "file": file,
            "duration_seconds": video["duration_seconds"],
            "width": video["width"],
            "height": video["height"],
        }
        if video
        else None,
        "voice": detail["voice"],
        "shots": len(detail["shots"]),
        "credits": detail["credits"],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"{detail['title'] or run_id} · {detail['status']}")
        if detail["error"]:
            print(f"Error: {detail['error']}")
        if video:
            print(f"  file: {file}")
            size = f"{video['width']}x{video['height']}"
            print(f"  {video['duration_seconds']}s, {size}, {payload['shots']} shots")
        if detail["credits"]:
            print(f"  footage: {len(detail['credits'])} Pexels clips (credits in --json)")
    return 0 if detail["status"] == "completed" else 1


def cmd_runs(args: argparse.Namespace) -> int:
    from shortstock import db

    runs = db.list_runs()
    if args.json:
        print(json.dumps(runs, indent=2, ensure_ascii=False))
        return 0
    for run in runs:
        print(f"{run['id']}  {run['status']:<10} {run['created_at'][:16]}  {run['title'] or '(untitled)'}")
    if not runs:
        print("No runs yet. Try: shortstock make script.md")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    _require_run(args.run_id)
    args.out = None
    return _report(args, args.run_id)


def cmd_delete(args: argparse.Namespace) -> int:
    from shortstock import pipeline

    run = _require_run(args.run_id)
    if run["status"] == "running":
        raise RuntimeError("That run is still running")
    pipeline.delete(run["id"])
    print(f"Deleted {run['id']}")
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    from shortstock.tts import Fish, get_voice

    voice = get_voice(args.provider, voice_id="list")
    voices = voice.voices(args.search) if isinstance(voice, Fish) else voice.voices()
    if args.json:
        print(json.dumps(voices, indent=2))
    else:
        for v in voices:
            print(f"{v['id']}  {v['name']}  {v['description']}")
    return 0


def cmd_footage(args: argparse.Namespace) -> int:
    from shortstock.config import get_setting
    from shortstock.footage import orientation_for, search

    clips = search(args.query, orientation_for(args.aspect), get_setting("pexels_api_key"))[:10]
    if args.json:
        print(json.dumps(clips, indent=2))
    else:
        for c in clips:
            print(f"[clip: {c['id']}]  {c['duration']:.0f}s  {c['width']}x{c['height']}  {c['page']}")
    return 0


def cmd_config_list(args: argparse.Namespace) -> int:
    from shortstock import db
    from shortstock.config import SETTINGS, get_setting, mask

    rows = []
    for key, spec in SETTINGS.items():
        value = get_setting(key)
        rows.append(
            {
                "key": key,
                "value": mask(value) if spec.secret else value,
                "saved": db.get_setting(key) is not None,
                "env": spec.env,
                "description": spec.description,
            }
        )
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(f"{row['key']:<24} {row['value'] or '-':<32} {row['description']}")
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    from shortstock import db
    from shortstock.config import SETTINGS

    if args.key not in SETTINGS:
        raise RuntimeError(f"Unknown setting '{args.key}'. Run `shortstock config list`.")
    db.set_setting(args.key, args.value)
    print(f"Saved {args.key}")
    return 0


def cmd_config_unset(args: argparse.Namespace) -> int:
    from shortstock import db
    from shortstock.config import SETTINGS

    if args.key not in SETTINGS:
        raise RuntimeError(f"Unknown setting '{args.key}'")
    db.set_setting(args.key, None)
    print(f"Cleared {args.key}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from shortstock.doctor import checks

    results = checks()
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for c in results:
            mark = "ok " if c["ok"] else ("ERR" if c["required"] else " - ")
            print(f"[{mark}] {c['name']:<9} {c['detail']}")
    return 0 if all(c["ok"] for c in results if c["required"]) else 1


def cmd_channels(args: argparse.Namespace) -> int:
    from shortstock.publish import BufferClient

    channels = BufferClient().channels()
    if args.json:
        print(json.dumps(channels, indent=2))
    else:
        for ch in channels:
            print(f"{ch['id']}  {ch['service']:<10} {ch['name']}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from shortstock.publish import publish_video

    at = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else None
    posts = publish_video(args.video_id, args.channels, args.mode, at)
    if args.json:
        print(json.dumps(posts, indent=2))
    else:
        for post in posts:
            print(
                f"{post['channel_name'] or post['channel_id']}: {post['status']}"
                + (f" ({post['error']})" if post.get("error") else "")
            )
    return 0 if all(p["status"] != "failed" for p in posts) else 1


# ── helpers ──────────────────────────────────────────────────────────────────


def _require_run(run_id: str) -> dict:
    from shortstock import db

    run = db.get_run(run_id)
    if run is None:
        raise RuntimeError(f"No run with id {run_id}")
    return run


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _emit(args: argparse.Namespace, payload: dict, text: str) -> None:
    print(json.dumps(payload) if args.json else text)


def _fail(message: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"error": message}))
    else:
        print(f"Error: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

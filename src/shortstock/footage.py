"""Stock footage from Pexels, cached in a local stock bank so clips are reused across videos."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from shortstock.config import stock_dir

logger = logging.getLogger(__name__)

API = "https://api.pexels.com/videos"
FALLBACK_QUERIES = ["abstract background", "city timelapse", "nature landscape", "people walking"]
_CACHE_SECONDS = 3600
_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


class FootageError(RuntimeError):
    pass


def orientation_for(aspect: str) -> str:
    return {"9:16": "portrait", "4:5": "portrait", "1:1": "square", "16:9": "landscape"}[aspect]


def search(query: str, orientation: str, api_key: str, target: int = 1080, transport=None) -> list[dict]:
    """Search Pexels videos. Results are cached for an hour to spare the API quota."""
    if not api_key:
        raise FootageError("Add a free Pexels API key in Settings so shortstock can find footage")
    key = (query.strip().lower(), orientation)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    with httpx.Client(timeout=30, headers={"Authorization": api_key}, transport=transport) as client:
        try:
            response = client.get(
                f"{API}/search", params={"query": query, "orientation": orientation, "per_page": 15}
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise FootageError("Pexels rejected the API key. Check it in Settings.") from exc
            logger.warning("Pexels search failed for %r: %s", query, exc)
            return []
        except httpx.HTTPError as exc:
            logger.warning("Pexels search failed for %r: %s", query, exc)
            return []
    results = [v for v in (_normalise(item, target) for item in response.json().get("videos", [])) if v]
    _cache[key] = (time.time(), results)
    return results


def get_video(video_id: int, api_key: str, target: int = 1080, transport=None) -> dict:
    with httpx.Client(timeout=30, headers={"Authorization": api_key}, transport=transport) as client:
        response = client.get(f"{API}/videos/{video_id}")
    if response.status_code == 404:
        raise FootageError(f"Pexels video {video_id} does not exist")
    response.raise_for_status()
    video = _normalise(response.json(), target)
    if video is None:
        raise FootageError(f"Pexels video {video_id} has no downloadable files")
    return video


def _normalise(item: dict, target: int) -> dict | None:
    files = [f for f in item.get("video_files", []) if f.get("link") and f.get("width")]
    if not files:
        return None

    def short_side(f: dict) -> int:
        return min(int(f["width"]), int(f.get("height") or f["width"]))

    big_enough = [f for f in files if short_side(f) >= min(target, 1080)]
    best = min(big_enough, key=short_side) if big_enough else max(files, key=short_side)
    smallest = min(files, key=short_side)
    return {
        "id": int(item["id"]),
        "duration": float(item.get("duration") or 0),
        "width": int(item.get("width") or 0),
        "height": int(item.get("height") or 0),
        "url": best["link"],
        "preview": smallest["link"],
        "image": item.get("image", ""),
        "author": (item.get("user") or {}).get("name", "Pexels"),
        "page": item.get("url", ""),
    }


def fill_shots(
    shots: list[dict],
    api_key: str,
    aspect: str,
    target: int,
    transport=None,
    avoid: set[int] | None = None,
) -> dict:
    """Pick a different stock clip for every shot and download it into the stock bank.

    A shot with a ``pin`` (a Pexels id locked in the script) uses exactly that video.
    Clips in ``avoid`` (used by earlier cuts of this video) are only chosen when nothing else fits.
    """
    avoid = avoid or set()
    if not api_key:
        raise FootageError("Add a free Pexels API key in Settings so shortstock can find footage")
    orientation = orientation_for(aspect)
    used: set[int] = {s["pin"] for s in shots if s.get("pin")}
    credits: dict[int, dict] = {}
    for shot in shots:
        if shot.get("pin"):
            video = get_video(shot["pin"], api_key, target, transport)
            shot["matched_query"] = f"clip {video['id']}"
        else:
            video = None
            for query in [shot["query"], *FALLBACK_QUERIES]:
                candidates = [
                    v for v in search(query, orientation, api_key, target, transport) if v["id"] not in used
                ]
                # Fresh clips first, then ones long enough for the shot.
                candidates.sort(key=lambda v: (v["id"] in avoid, v["duration"] < shot["duration"]))
                if candidates:
                    video = candidates[0]
                    shot["matched_query"] = query
                    break
            if video is None:
                raise FootageError(f"No stock footage found for '{shot['query']}'")
            used.add(video["id"])
        shot["clip_path"] = str(download(video, transport))
        shot["clip_id"] = video["id"]
        shot["thumb"] = video["image"]
        credits[video["id"]] = {"author": video["author"], "url": video["page"]}
    return {"shots": shots, "credits": [{"id": k, **v} for k, v in credits.items()]}


def download(video: dict, transport=None) -> Path:
    """Download once into the stock bank; later videos reuse the file."""
    bank = stock_dir() / "pexels"
    bank.mkdir(parents=True, exist_ok=True)
    path = bank / f"{video['id']}.mp4"
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_suffix(".part")
    with httpx.Client(timeout=180, follow_redirects=True, transport=transport) as client:
        with client.stream("GET", video["url"]) as response:
            response.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
    tmp.replace(path)
    (bank / f"{video['id']}.json").write_text(
        json.dumps({"author": video["author"], "page": video["page"], "source": "pexels"}), encoding="utf-8"
    )
    return path

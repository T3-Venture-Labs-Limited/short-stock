"""SQLite storage for runs, stages, videos, posts and settings."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    script TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL,
    current_stage TEXT,
    error TEXT,
    options TEXT NOT NULL,
    claimed_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stages (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    PRIMARY KEY (run_id, name)
);
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    file_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    duration_seconds REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    service TEXT,
    mode TEXT NOT NULL,
    scheduled_at TEXT,
    status TEXT NOT NULL,
    buffer_post_id TEXT,
    media_url TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

JSON_FIELDS = {"options", "hashtags"}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


_initialized: set[str] = set()
_init_lock = threading.Lock()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    from shortstock.config import home

    path = str(home() / "shortstock.db")
    with _init_lock:  # create the schema once per process, and again if the file was deleted
        if path not in _initialized or not os.path.exists(path):
            init = sqlite3.connect(path, timeout=30)
            try:
                init.execute("PRAGMA journal_mode = WAL")
                init.executescript(SCHEMA)
            finally:
                init.close()
            _initialized.add(path)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in JSON_FIELDS & data.keys():
        data[key] = json.loads(data[key]) if data[key] else None
    return data


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [_row(r) for r in rows]  # type: ignore[misc]


def _update(table: str, row_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    values = [json.dumps(v) if k in JSON_FIELDS else v for k, v in fields.items()]
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", [*values, row_id])


# ── runs ─────────────────────────────────────────────────────────────────────


def create_run(
    script: str, options: dict[str, Any], title: str | None = None, status: str = "queued"
) -> dict[str, Any]:
    run_id, ts = new_id(), now()
    claimed = os.getpid() if status == "running" else None
    with connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, script, title, status, options, claimed_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, script, title, status, json.dumps(options), claimed, ts, ts),
        )
    return get_run(run_id)  # type: ignore[return-value]


def get_run(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())


def list_runs(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT r.*, v.id AS video_id, v.duration_seconds FROM runs r "
            "LEFT JOIN videos v ON v.run_id = r.id ORDER BY r.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return _rows(rows)


def update_run(run_id: str, **fields: Any) -> None:
    _update("runs", run_id, {**fields, "updated_at": now()})


def delete_run(run_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))


def claim_next_run() -> dict[str, Any] | None:
    """Atomically move the oldest queued run to ``running``."""
    with connect() as conn:
        row = conn.execute(
            "UPDATE runs SET status = 'running', error = NULL, claimed_by = ?, updated_at = ? WHERE id = ("
            "SELECT id FROM runs WHERE status = 'queued' ORDER BY created_at LIMIT 1) RETURNING *",
            (os.getpid(), now()),
        ).fetchone()
    return _row(row)


def queue_counts() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM runs WHERE status IN ('queued', 'running') GROUP BY status"
        ).fetchall()
    counts = {"queued": 0, "running": 0}
    counts.update({r["status"]: r["n"] for r in rows})
    return counts


def requeue_interrupted_runs() -> None:
    """Runs left ``running`` by a process that no longer exists go back to the queue and resume.

    Runs owned by a live process (for example a foreground ``shortstock make``) are left alone.
    """
    with connect() as conn:
        rows = conn.execute("SELECT id, claimed_by FROM runs WHERE status = 'running'").fetchall()
        for row in rows:
            if row["claimed_by"] and _alive(row["claimed_by"]):
                continue
            conn.execute("UPDATE runs SET status = 'queued', claimed_by = NULL WHERE id = ?", (row["id"],))
            conn.execute(
                "UPDATE stages SET status = 'pending' WHERE run_id = ? AND status = 'running'", (row["id"],)
            )


def _alive(pid: int) -> bool:
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ── stages ───────────────────────────────────────────────────────────────────


def set_stage(run_id: str, name: str, status: str, error: str | None = None) -> None:
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO stages (run_id, name, status, error, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, name) DO UPDATE SET "
            "status = excluded.status, error = excluded.error, "
            "started_at = COALESCE(CASE WHEN excluded.status = 'running' THEN excluded.started_at END,"
            " stages.started_at), finished_at = excluded.finished_at",
            (
                run_id,
                name,
                status,
                error,
                ts if status == "running" else None,
                ts if status in {"done", "failed", "skipped"} else None,
            ),
        )


def list_stages(run_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return _rows(conn.execute("SELECT * FROM stages WHERE run_id = ?", (run_id,)).fetchall())


# ── videos ───────────────────────────────────────────────────────────────────


def save_video(run_id: str, **fields: Any) -> dict[str, Any]:
    row = {"id": new_id(), "run_id": run_id, "created_at": now(), **fields}
    row["hashtags"] = json.dumps(row.get("hashtags") or [])
    with connect() as conn:
        conn.execute("DELETE FROM videos WHERE run_id = ?", (run_id,))
        conn.execute(
            f"INSERT INTO videos ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
            list(row.values()),
        )
    return get_video(row["id"])  # type: ignore[return-value]


def get_video(video_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone())


def video_for_run(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM videos WHERE run_id = ?", (run_id,)).fetchone())


# ── posts ────────────────────────────────────────────────────────────────────


def create_post(**fields: Any) -> dict[str, Any]:
    row = {"id": new_id(), "created_at": now(), **fields}
    with connect() as conn:
        conn.execute(
            f"INSERT INTO posts ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
            list(row.values()),
        )
    return row


def list_posts(video_id: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT p.* FROM posts p JOIN videos v ON v.id = p.video_id"
    args: list[str] = []
    if video_id:
        query += " WHERE p.video_id = ?"
        args.append(video_id)
    elif run_id:
        query += " WHERE v.run_id = ?"
        args.append(run_id)
    with connect() as conn:
        return _rows(conn.execute(query + " ORDER BY p.created_at DESC", args).fetchall())


# ── settings ─────────────────────────────────────────────────────────────────


def get_setting(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str | None) -> None:
    with connect() as conn:
        if value:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))

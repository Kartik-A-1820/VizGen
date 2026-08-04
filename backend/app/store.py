from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH, ensure_runtime_dirs


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    ensure_runtime_dirs()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                model_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                prompt TEXT NOT NULL,
                negative_prompt TEXT NOT NULL DEFAULT '',
                params_json TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                output_json TEXT NOT NULL DEFAULT '[]',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "mode" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN mode TEXT NOT NULL DEFAULT 'generate'")
        # Staged-pipeline UI fields (load/enhance/generate/scale progression + ETA).
        for col, ddl in (
            ("stage", "TEXT NOT NULL DEFAULT ''"),
            ("stage_index", "INTEGER NOT NULL DEFAULT 0"),
            ("stage_total", "INTEGER NOT NULL DEFAULT 1"),
            ("eta_seconds", "REAL NOT NULL DEFAULT 0"),
        ):
            if col not in columns:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")


def row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "mode" not in data and "kind" in data:
        data["mode"] = data["kind"]
    data["params"] = json.loads(data.pop("params_json"))
    data["outputs"] = json.loads(data.pop("output_json"))
    return data


def create_job(
    job_id: str,
    model_id: str,
    mode: str,
    prompt: str,
    negative_prompt: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, status, model_id, mode, prompt, negative_prompt,
                params_json, created_at, updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, model_id, mode, prompt, negative_prompt, json.dumps(params), now, now),
        )
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return row_to_job(row)


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_job(row) for row in rows]


def list_active_jobs(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status IN ('queued', 'running')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_job(row) for row in rows]


def next_queued_job() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
    return row_to_job(row) if row else None


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    if not fields:
        return get_job(job_id)

    fields["updated_at"] = utc_now()
    if "params" in fields:
        fields["params_json"] = json.dumps(fields.pop("params"))
    if "outputs" in fields:
        fields["output_json"] = json.dumps(fields.pop("outputs"))

    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values())
    values.append(job_id)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
    return get_job(job_id)


def cancel_queued_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job["status"] != "queued":
        raise ValueError("Only queued jobs can be cancelled")
    return update_job(job_id, status="cancelled", progress=100, message="Job cancelled")


def delete_job(job_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def queue_position(job_id: str) -> int | None:
    job = get_job(job_id)
    if job["status"] != "queued":
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS ahead
            FROM jobs
            WHERE status = 'queued'
              AND created_at < (SELECT created_at FROM jobs WHERE id = ?)
            """,
            (job_id,),
        ).fetchone()
    return int(row["ahead"]) + 1

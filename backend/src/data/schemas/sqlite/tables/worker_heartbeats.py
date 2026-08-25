"""`worker_heartbeats` — worker process health probe tablosu."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active_job_id CHAR(36) NULL,
    scheduler_last_run_at TEXT NULL
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


worker_heartbeats_migration = Migration(version=4, name="worker_heartbeats", apply=apply)

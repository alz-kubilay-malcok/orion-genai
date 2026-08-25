"""`outbox_jobs` — outbox pattern tablosu."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS outbox_jobs (
    id CHAR(36) PRIMARY KEY,
    job_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL DEFAULT 'request',
    aggregate_id CHAR(36) REFERENCES requests(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL DEFAULT (datetime('now')),
    lease_owner TEXT,
    leased_until TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    CONSTRAINT outbox_jobs_status_check CHECK (status IN
        ('pending', 'processing', 'retry', 'completed', 'dead_letter')),
    CONSTRAINT outbox_jobs_attempts_check CHECK (attempts >= 0),
    CONSTRAINT outbox_jobs_max_attempts_check CHECK (max_attempts >= 1),
    CONSTRAINT outbox_jobs_lease_check CHECK (
        (status = 'processing' AND lease_owner IS NOT NULL
         AND leased_until IS NOT NULL)
        OR status <> 'processing'
    )
);

CREATE INDEX IF NOT EXISTS outbox_poll_idx
    ON outbox_jobs (available_at, created_at);
CREATE INDEX IF NOT EXISTS outbox_lease_recovery_idx
    ON outbox_jobs (leased_until)
    WHERE status = 'processing';
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


outbox_jobs_migration = Migration(version=10, name="outbox_jobs", apply=apply)

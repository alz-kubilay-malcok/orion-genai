"""`audit_events` — request lifecycle olay günlüğü."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL REFERENCES requests(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    request_version INTEGER NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS audit_events_request_idx
    ON audit_events (request_id, created_at);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


audit_events_migration = Migration(version=9, name="audit_events", apply=apply)

"""`request_revisions` — client-facing snapshot."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS request_revisions (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL,
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT request_revisions_request_version_uidx UNIQUE (request_id, version)
);

CREATE INDEX IF NOT EXISTS request_revisions_request_idx
    ON request_revisions (request_id);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


request_revisions_migration = Migration(version=12, name="request_revisions", apply=apply)

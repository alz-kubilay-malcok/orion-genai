"""`request_revisions` — client-facing snapshot, revize maili diff'i için."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS request_revisions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL,
    version INTEGER NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT request_revisions_request_version_uidx UNIQUE (request_id, version)
);

CREATE INDEX IF NOT EXISTS request_revisions_request_idx
    ON request_revisions (request_id);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


request_revisions_migration = Migration(version=12, name="request_revisions", apply=apply)

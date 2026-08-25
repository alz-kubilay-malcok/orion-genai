"""`config_approvers` — admin onay scope listesi."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS config_approvers (
    id CHAR(36) PRIMARY KEY,
    email TEXT NOT NULL,
    scope TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT config_approvers_scope_check
        CHECK (scope IN ('GENAI_APPROVAL', 'CHATBOT_ASSIGNMENT')),
    CONSTRAINT config_approvers_email_scope_uidx UNIQUE (email, scope)
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


config_approvers_migration = Migration(version=3, name="config_approvers", apply=apply)

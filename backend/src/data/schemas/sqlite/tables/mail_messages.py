"""`mail_messages` — DB-backed mail adapter mailbox.

`read_by_user_id`: auth strip sonrası `users` tablosu kaldırıldı; alan
FK'sız bırakıldı, ileride LDAP geldiğinde `users` tablosu tekrar ihdas
edilebilir ve bu migration'a FK back-fill eklenir.
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS mail_messages (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) REFERENCES requests(id) ON DELETE SET NULL,
    template VARCHAR(64) NOT NULL,
    subject TEXT NOT NULL,
    from_email TEXT NOT NULL,
    recipients TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '{}',
    body_text TEXT,
    body_html TEXT,
    has_secret INTEGER NOT NULL DEFAULT 0,
    correlation_id TEXT,
    app_env VARCHAR(16) NOT NULL,
    delivery_status VARCHAR(16) NOT NULL DEFAULT 'skipped',
    read_at TEXT,
    read_by_user_id CHAR(36),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT mail_messages_delivery_status_check
        CHECK (delivery_status IN ('pending', 'sent', 'failed', 'skipped'))
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


mail_messages_migration = Migration(version=11, name="mail_messages", apply=apply)

"""`mail_messages` — DB-backed mail adapter'ın mailbox için yazdığı tablo.

`read_by_user_id`: auth strip sonrası `users` tablosu kaldırıldı; alan FK'sız
bırakıldı. LDAP gelince `users` tekrar ihdas edilip bu sütuna FK
back-fill migration'ı eklenecek.
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS mail_messages (
    id UUID PRIMARY KEY,
    request_id UUID REFERENCES requests(id) ON DELETE SET NULL,
    template VARCHAR(64) NOT NULL,
    subject TEXT NOT NULL,
    from_email TEXT NOT NULL,
    recipients TEXT[] NOT NULL,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    body_text TEXT,
    body_html TEXT,
    has_secret BOOLEAN NOT NULL DEFAULT FALSE,
    correlation_id TEXT,
    app_env VARCHAR(16) NOT NULL,
    delivery_status VARCHAR(16) NOT NULL DEFAULT 'skipped',
    read_at TIMESTAMPTZ,
    read_by_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mail_messages_delivery_status_check
        CHECK (delivery_status IN ('pending', 'sent', 'failed', 'skipped')),
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


mail_messages_migration = Migration(version=11, name="mail_messages", apply=apply)

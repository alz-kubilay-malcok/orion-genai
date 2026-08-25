"""`approval_tokens` — tek-kullanımlık token."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS approval_tokens (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,
    action TEXT NOT NULL,
    token_hash BLOB NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    invalidated_at TEXT,
    invalidation_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT approval_tokens_action_check
        CHECK (action IN ('approve', 'revise', 'reject')),
    CONSTRAINT approval_tokens_request_type_check CHECK (request_type IN
        ('litellm_key', 'mcp_key', 'mcp_server_registry', 'chatbot_support')),
    CONSTRAINT approval_tokens_expiry_check
        CHECK (expires_at > issued_at),
    CONSTRAINT approval_tokens_hash_uidx UNIQUE (token_hash),
    CONSTRAINT approval_tokens_request_action_uidx UNIQUE (request_id, action)
);

CREATE INDEX IF NOT EXISTS approval_tokens_request_idx
    ON approval_tokens (request_id);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


approval_tokens_migration = Migration(version=7, name="approval_tokens", apply=apply)

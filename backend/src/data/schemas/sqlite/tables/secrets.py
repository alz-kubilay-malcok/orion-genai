"""`secrets` — AES-GCM şifreli blob deposu."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS secrets (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL UNIQUE REFERENCES requests(id) ON DELETE RESTRICT,
    secret_type TEXT NOT NULL,
    provider_token_id TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    nonce BLOB NOT NULL,
    auth_tag BLOB NOT NULL,
    key_hint CHAR(4) NOT NULL,
    key_version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT secrets_type_check
        CHECK (secret_type IN ('litellm_key', 'mcp_key'))
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


secrets_migration = Migration(version=8, name="secrets", apply=apply)

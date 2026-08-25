"""`secrets` — provider API anahtarlarının AES-GCM şifreli blob deposu."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS secrets (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE REFERENCES requests(id) ON DELETE RESTRICT,
    secret_type TEXT NOT NULL,
    provider_token_id TEXT NOT NULL,
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    auth_tag BYTEA NOT NULL,
    key_hint CHAR(4) NOT NULL,
    key_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT secrets_type_check
        CHECK (secret_type IN ('litellm_key', 'mcp_key'))
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


secrets_migration = Migration(version=8, name="secrets", apply=apply)

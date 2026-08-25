"""`approval_tokens` — admin/reviewer için tek-kullanımlık token."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS approval_tokens (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type request_type NOT NULL,
    action TEXT NOT NULL,
    token_hash BYTEA NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT approval_tokens_action_check
        CHECK (action IN ('approve', 'revise', 'reject')),
    CONSTRAINT approval_tokens_expiry_check
        CHECK (expires_at > issued_at),
    CONSTRAINT approval_tokens_hash_uidx UNIQUE (token_hash),
    CONSTRAINT approval_tokens_request_action_uidx UNIQUE (request_id, action)
);

CREATE INDEX IF NOT EXISTS approval_tokens_request_idx
    ON approval_tokens (request_id);

-- Sadece kullanılmamış, geçerli token'ların expiry sweep'ini hızlandırmak için.
CREATE INDEX IF NOT EXISTS approval_tokens_expiry_idx
    ON approval_tokens (expires_at)
    WHERE used_at IS NULL AND invalidated_at IS NULL;
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


approval_tokens_migration = Migration(version=7, name="approval_tokens", apply=apply)

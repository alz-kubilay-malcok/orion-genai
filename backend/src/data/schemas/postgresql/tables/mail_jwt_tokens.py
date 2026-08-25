"""`mail_jwt_tokens` — `core.mailing.jwt_mail` çıktısı için DB policy katmanı.

Tek-kullanım (`used_at` flip) + manuel revoke (`revoked_at`) +
audit (`recipient`) için salt PG tarafı.
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS mail_jwt_tokens (
    id UUID PRIMARY KEY,
    jti VARCHAR(36) NOT NULL,
    token_hash BYTEA NOT NULL,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type VARCHAR(32) NOT NULL,
    action TEXT NOT NULL,
    recipient TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mail_jwt_tokens_jti_uidx UNIQUE (jti),
    CONSTRAINT mail_jwt_tokens_hash_uidx UNIQUE (token_hash),
    CONSTRAINT mail_jwt_tokens_action_check
        CHECK (action IN ('approve', 'revise', 'reject')),
    CONSTRAINT mail_jwt_tokens_request_type_check
        CHECK (request_type IN ('litellm_key', 'mcp_key')),
    CONSTRAINT mail_jwt_tokens_expiry_check
        CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS mail_jwt_tokens_request_idx
    ON mail_jwt_tokens (request_id);

-- Replay sweep / temizlik için: hâlâ aktif olan token'ların süresi.
CREATE INDEX IF NOT EXISTS mail_jwt_tokens_active_expiry_idx
    ON mail_jwt_tokens (expires_at)
    WHERE used_at IS NULL AND revoked_at IS NULL;
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


mail_jwt_tokens_migration = Migration(
    version=14, name="mail_jwt_tokens", apply=apply,
)

"""`mail_jwt_tokens` — SQLite port.

mime type'lar sqlite'a göre sadeleştirildi:
- UUID → CHAR(36)
- BYTEA → BLOB
- VARCHAR → TEXT
- TIMESTAMPTZ → ISO-8601 TEXT (`UtcDateTime` zaten konvert eder)
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS mail_jwt_tokens (
    id CHAR(36) PRIMARY KEY,
    jti TEXT NOT NULL,
    token_hash BLOB NOT NULL,
    request_id CHAR(36) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,
    action TEXT NOT NULL,
    recipient TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    revoked_at TEXT,
    revoked_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
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

CREATE INDEX IF NOT EXISTS mail_jwt_tokens_active_expiry_idx
    ON mail_jwt_tokens (expires_at)
    WHERE used_at IS NULL AND revoked_at IS NULL;
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


mail_jwt_tokens_migration = Migration(
    version=14, name="mail_jwt_tokens", apply=apply,
)

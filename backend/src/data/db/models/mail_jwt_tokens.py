"""`MailJwtToken` ORM model — mail-issued capability token'ları için
DB policy katmanı.

`jwt_mail.issue(...)` çıktısı (compact_token + jti + hash) bu tabloya
yazılır; `MailJwtValidator.validate_and_consume(...)` ise:

- replay'i (`used_at` IS NULL),
- manuel revoke'u (`revoked_at` IS NULL),
- audit trail'i (recipient / request context)

…buradan enforce eder. JWT imzası sahiplik/taşıyıcılık sağlar; tablo
davranışı (single-use, revoke edilebilir, denetlenebilir) sağlar.

Tip konvansiyonları:
- `UtcDateTime` cross-dialect (PG TIMESTAMPTZ ↔ SQLite TEXT) otomatik
  tz-normalize eder.
- `token_hash` `LargeBinary` — sha256(compact_token) (32 byte).
- `Uuid` cross-dialect UUID tip'i.

DDL migration hâlâ TBD — repo kökü `db_schema_update_notes.md`'ye bak.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class MailJwtToken(Base):
    __tablename__ = "mail_jwt_tokens"
    __table_args__ = (
        CheckConstraint(
            "action IN ('approve', 'revise', 'reject')",
            name="mail_jwt_tokens_action_check",
        ),
        CheckConstraint(
            "request_type IN ('litellm_key', 'mcp_key')",
            name="mail_jwt_tokens_request_type_check",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="mail_jwt_tokens_expiry_check",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)

    # `jti` claim'i; UUID → CHAR(36) SQLite'ta, native UUID PG'de.
    jti: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    # sha256(compact_token); secondary lookup + paranoia check.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)

    request_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)

    issued_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)

    used_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    revoked_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["MailJwtToken"]

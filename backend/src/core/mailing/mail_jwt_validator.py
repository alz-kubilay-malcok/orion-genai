"""DB-backed politika katmanı — `issue()`/`decode()`'u tek-kullanım
semantiğine bağlar.

Akış:
1. `decode(compact_token)` → imza + `exp` (delegated to `jwt_mail`).
2. DB'de `jti` veya `token_hash` ile satırı bul.
3. `used_at` / `revoked_at` kontrolü.
4. UPDATE `used_at = now()` ile atomik flip; race'te rowcount==0 hard reject.
5. Claim özetini `MailJwtHandle` olarak döndür.

Transaction sınırı çağıranındadır (`session` flush/rollback'in sahibi
route handler veya use-case).

ORM model tarafı: `data.db.models.mail_jwt_tokens.MailJwtToken`.
DDL migration: repo kökü `db_schema_update_notes.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...data.db.models.mail_jwt_tokens import MailJwtToken
from .jwt_mail import (
    MailJwtError,
    decode,
    hash_compact_token,
)


# ---- Caller-facing DTO --------------------------------------------------


@dataclass(frozen=True, slots=True)
class MailJwtHandle:
    """Validate sonrası route handler'a verilen minimum claim görünümü."""

    jti: str
    request_id: str
    request_type: str
    action: str
    recipient: str
    expires_at: datetime


# ---- Validator ----------------------------------------------------------


class MailJwtValidator:
    """Stateless helper — di'ye registration gerekmiyorsa direkt class
    olarak kullanılır; state tutmaz.
    """

    async def validate_and_consume(
        self,
        session: AsyncSession,
        compact_token: str,
    ) -> MailJwtHandle:
        """İmzayı + DB state'i doğrula; `used_at`'i flip et.

        Raises:
            MailJwtError: alt tipleri —
                `MailJwtSignatureError` bilinmeyen/tampered/used/revoked.
                `MailJwtExpiredError` süresi geçmiş.
        """
        claims = decode(compact_token)

        jti = claims["jti"]
        token_hash = hash_compact_token(compact_token)

        row = await session.scalar(
            select(MailJwtToken).where(
                (MailJwtToken.jti == jti)
                | (MailJwtToken.token_hash == token_hash)
            )
        )
        if row is None:
            raise MailJwtError("unknown token (DB row yok)")
        if row.revoked_at is not None:
            raise MailJwtError(f"token revoked: {row.revoked_reason or 'n/a'}")
        if row.used_at is not None:
            raise MailJwtError("token already used")

        # Atomik tek-kullanım flip'i; where-clause `used_at IS NULL`
        # koşulu ile race'i DB'ye havale ediyoruz.
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await session.execute(
            update(MailJwtToken)
            .where(MailJwtToken.jti == jti, MailJwtToken.used_at.is_(None))
            .values(used_at=now_naive)
        )
        if result.rowcount == 0:
            raise MailJwtError("token already used (race)")

        return MailJwtHandle(
            jti=jti,
            request_id=claims["sub"],
            request_type=claims["typ"],
            action=claims["act"],
            recipient=claims["rec"],
            expires_at=datetime.utcfromtimestamp(int(claims["exp"])),
        )


__all__ = ["MailJwtHandle", "MailJwtValidator", "MailJwtError"]

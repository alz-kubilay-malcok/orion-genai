"""Mail capability JWT — PyJWT (HS256) imza/veri katmanı.

Bu modül **yalnız kriptografik geçerlilik** ile ilgilenir;
tek-kullanım / manuel revoke semantiği `mail_jwt_validator` katmanındadır.

Env sözleşmesi:
- `MAIL_JWT_SECRET`   : HS256 secret. Boş/eksik → `MailJwtConfigError`.
- `MAIL_JWT_TTL_DAYS` : varsayılan token ömrü (gün); `issue(...)` isterse
                        `ttl` parametresiyle override edebilir.

Claim sözleşmesi (`issue()` tarafından imzalanır):
- `jti`  : tekil token UUID'si; DB `mail_jwt_tokens.jti` ile eşleşir.
- `sub`  : request_id (UUID, string form).
- `typ`  : request_type (`litellm_key` | `mcp_key`).
- `act`  : action (`approve` | `revise` | `reject`).
- `rec`  : alıcı email.
- `iat`  : UTC epoch int.
- `exp`  : UTC epoch int.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt


# ---- Errors -------------------------------------------------------------


class MailJwtError(Exception):
    """Base error."""


class MailJwtConfigError(MailJwtError):
    """Env'de eksik/geçersiz konfig."""


class MailJwtExpiredError(MailJwtError):
    """`exp` claim'i geçmişte."""


class MailJwtSignatureError(MailJwtError):
    """İmza tutmuyor — token değiştirilmiş veya yanlış secret."""


class MailJwtMalformedError(MailJwtError):
    """Segment/claim parse edilemedi."""


# ---- Env helpers --------------------------------------------------------


def _resolve_secret() -> str:
    raw = os.getenv("MAIL_JWT_SECRET", "").strip()
    if not raw:
        raise MailJwtConfigError(
            "MAIL_JWT_SECRET env tanımsız; mail JWT imzalanamaz"
        )
    return raw


def _resolve_default_ttl() -> timedelta:
    raw = os.getenv("MAIL_JWT_TTL_DAYS", "7").strip()
    try:
        days = int(raw)
    except ValueError as exc:
        raise MailJwtConfigError(
            f"MAIL_JWT_TTL_DAYS int değil: {raw!r}"
        ) from exc
    if days <= 0:
        raise MailJwtConfigError(
            f"MAIL_JWT_TTL_DAYS > 0 olmalı, gelen: {days}"
        )
    return timedelta(days=days)


def hash_compact_token(compact_token: str) -> bytes:
    """DB `mail_jwt_tokens.token_hash` için sha256 digest.

    PyJWT `encode()` aynı payload + secret için deterministik compact
    string döndürür → bu hash stable.
    """
    return hashlib.sha256(compact_token.encode("ascii")).digest()


# ---- Public types -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IssuedMailJwt:
    """`issue()` çıktısı."""

    compact_token: str
    jti: str
    token_hash: bytes
    issued_at: datetime
    expires_at: datetime


# ---- Public API ---------------------------------------------------------


_ALG = "HS256"
_REQUIRED_CLAIMS = ("jti", "sub", "typ", "act", "rec", "iat", "exp")


def issue(  # noqa: PLR0913 — claim set'i sabit; tuple'da bw
    *,
    request_id: str,
    request_type: str,
    action: str,
    recipient: str,
    extra_claims: dict[str, Any] | None = None,
    now: datetime | None = None,
    ttl: timedelta | None = None,
) -> IssuedMailJwt:
    """Tek mail-link capability'si için JWT üret — side effect yok.

    DB yazımı çağıranın sorumluluğunda (`mail_jwt_validator` veya başka
    repo katmanı).
    """
    secret = _resolve_secret()
    if ttl is None:
        ttl = _resolve_default_ttl()
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    expires_at = issued_at + ttl
    jti = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "jti": jti,
        "sub": request_id,
        "typ": request_type,
        "act": action,
        "rec": recipient,
        "iat": issued_at,
        "exp": expires_at,
    }
    if extra_claims:
        payload.update(extra_claims)

    compact_token = jwt.encode(payload, secret, algorithm=_ALG)
    return IssuedMailJwt(
        compact_token=compact_token,
        jti=jti,
        token_hash=hash_compact_token(compact_token),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def decode(compact_token: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Signature + expiry kontrolü; claim dict'i döner.

    DB tarafı kontrolü (used/revoked) çağıranın sorumluluğunda.

    Args:
        compact_token: URL'den gelen `a.b.c` string.
        now:           TZ-aware UTC datetime; verilirse `exp` kontrolü
                       bu ana göre yapılır (test amaçlı). Verilmezse
                       PyJWT default davranışı (UTC `now()`).

    Raises:
        MailJwtSignatureError — segment/alg yanlış veya imza tutmuyor.
        MailJwtExpiredError   — `exp` geçmiş.
        MailJwtMalformedError — claim eksik veya parse edilemedi.
    """
    if compact_token.count(".") != 2:
        raise MailJwtSignatureError(
            "JWT üç segment bekliyor (head.payload.sig)"
        )

    secret = _resolve_secret()

    if now is not None:
        # Manuel exp kontrolü (test kolaylığı).
        try:
            claims = jwt.decode(
                compact_token,
                secret,
                algorithms=[_ALG],
                options={"verify_exp": False},
            )
        except jwt.InvalidSignatureError as exc:
            raise MailJwtSignatureError("imza uyuşmuyor") from exc
        except jwt.InvalidAlgorithmError as exc:
            raise MailJwtSignatureError(
                f"desteklenmeyen alg: {exc}"
            ) from exc
        except jwt.DecodeError as exc:
            raise MailJwtMalformedError(str(exc)) from exc

        exp = claims.get("exp")
        if not isinstance(exp, (int, float)):
            raise MailJwtMalformedError("exp claim eksik/yanlış tip")
        if now.timestamp() >= float(exp):
            raise MailJwtExpiredError("token süresi geçmiş")
    else:
        try:
            claims = jwt.decode(
                compact_token, secret, algorithms=[_ALG],
            )
        except jwt.ExpiredSignatureError as exc:
            raise MailJwtExpiredError("token süresi geçmiş") from exc
        except jwt.InvalidSignatureError as exc:
            raise MailJwtSignatureError("imza uyuşmuyor") from exc
        except jwt.InvalidAlgorithmError as exc:
            raise MailJwtSignatureError(
                f"desteklenmeyen alg: {exc}"
            ) from exc
        except jwt.DecodeError as exc:
            raise MailJwtMalformedError(str(exc)) from exc

    for required_key in _REQUIRED_CLAIMS:
        if required_key not in claims:
            raise MailJwtMalformedError(f"claim eksik: {required_key}")

    return claims


__all__ = [
    "IssuedMailJwt",
    "MailJwtError",
    "MailJwtConfigError",
    "MailJwtExpiredError",
    "MailJwtSignatureError",
    "MailJwtMalformedError",
    "decode",
    "hash_compact_token",
    "issue",
]

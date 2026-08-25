"""HMAC approval-token issue / hash / consume helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.adapters.crypto.signer import HmacTokenSigner
from backend.src.data.db.models.approval_tokens import ApprovalToken
from backend.src.domain.enums import VALID_ACTIONS_BY_TYPE, ApprovalAction, RequestType
from backend.src.domain.errors import InvalidActionTokenError


def hash_compact_token(compact: str) -> bytes:
    return hashlib.sha256(compact.encode("ascii")).digest()


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def issue_tokens_for_request(
    signer: HmacTokenSigner,
    *,
    request_id: UUID,
    request_type: str,
    ttl_hours: int,
) -> list[ApprovalToken]:
    """Sign one HMAC token per valid action and return unsaved ORM rows."""
    try:
        rtype = RequestType(request_type)
    except ValueError:
        return []
    actions = VALID_ACTIONS_BY_TYPE.get(rtype, frozenset())
    issued_at = _utcnow()
    expires_at = issued_at + timedelta(hours=ttl_hours)
    exp = int(expires_at.replace(tzinfo=UTC).timestamp())
    rows: list[ApprovalToken] = []
    for action in actions:
        compact = signer.sign({
            "request_id": str(request_id),
            "action": action.value,
            "request_type": request_type,
            "exp": exp,
            "nonce": secrets.token_urlsafe(12),
            "sub": "mail",
        })
        rows.append(
            ApprovalToken(
                id=uuid4(),
                request_id=request_id,
                request_type=request_type,
                action=action.value,
                token_hash=hash_compact_token(compact),
                issued_at=issued_at,
                expires_at=expires_at,
                created_at=issued_at,
            )
        )
        # stash compact on the instance for mail payload (not a mapped column)
        setattr(rows[-1], "_compact", compact)
    return rows


def compact_of(row: ApprovalToken) -> str:
    return str(getattr(row, "_compact", "") or "")


async def verify_token_against_db(
    session: AsyncSession,
    signer: HmacTokenSigner,
    compact: str,
    *,
    expected_action: str | None = None,
) -> tuple[dict[str, Any], ApprovalToken]:
    try:
        claims = signer.verify(compact)
    except InvalidActionTokenError:
        raise
    token_hash = hash_compact_token(compact)
    row = (await session.execute(
        select(ApprovalToken).where(ApprovalToken.token_hash == token_hash)
    )).scalar_one_or_none()
    if row is None:
        raise InvalidActionTokenError("token not registered")
    now = _utcnow()
    if _as_naive(row.expires_at) <= now:
        raise InvalidActionTokenError("token expired")
    if row.used_at is not None or row.invalidated_at is not None:
        raise InvalidActionTokenError("token already used")
    if expected_action and row.action != expected_action:
        raise InvalidActionTokenError("action mismatch")
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp <= now.replace(tzinfo=UTC).timestamp():
        raise InvalidActionTokenError("token expired")
    return claims, row


async def consume_winning_token(
    session: AsyncSession, winner: ApprovalToken, *, reason: str = "sibling_action_won",
) -> None:
    now = _utcnow()
    winner.used_at = now
    siblings = (await session.execute(
        select(ApprovalToken).where(
            ApprovalToken.request_id == winner.request_id,
            ApprovalToken.id != winner.id,
            ApprovalToken.used_at.is_(None),
            ApprovalToken.invalidated_at.is_(None),
        )
    )).scalars().all()
    for sibling in siblings:
        sibling.invalidated_at = now
        sibling.invalidation_reason = reason
    await session.flush()

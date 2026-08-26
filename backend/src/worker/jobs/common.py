"""Shared worker job helpers."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import PermanentError

logger = logging.getLogger(__name__)

def _secret_aad(request_id: uuid.UUID, secret_type: str) -> bytes:
    return f"{request_id}|{secret_type}|litellm".encode("utf-8")


async def _decrypt_request_secret(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    cipher: object | None,
) -> str:
    """Sonuç maili için plaintext; yoksa veya çözülemezse boş string."""
    if cipher is None or not hasattr(cipher, "decrypt"):
        return ""
    from sqlalchemy import select

    from ...data.db.models.secrets import Secret

    secret = await session.scalar(select(Secret).where(Secret.request_id == request_id))
    if secret is None:
        return ""
    try:
        plaintext = cipher.decrypt(  # type: ignore[union-attr]
            secret.nonce,
            secret.ciphertext,
            secret.auth_tag,
            aad=_secret_aad(request_id, secret.secret_type),
            key_version=secret.key_version,
        )
    except Exception:
        logger.exception(
            "secret decrypt failed",
            extra={"request_id": str(request_id)},
        )
        return ""
    if isinstance(plaintext, bytes):
        return plaintext.decode("utf-8")
    return str(plaintext or "")


def _require_uuid(payload: dict, field: str) -> uuid.UUID:
    raw = payload.get(field)
    if not raw:
        msg = f"payload alanı eksik: {field}"
        raise PermanentError(msg)
    try:
        return uuid.UUID(str(raw))
    except ValueError as exc:
        msg = f"payload alanı UUID değil: {field}={raw!r}"
        raise PermanentError(msg) from exc


async def _load_request(session: AsyncSession, request_id: uuid.UUID) -> dict | None:
    from sqlalchemy import select

    from ...data.db.models.requests import Request

    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is None:
        return None
    return {
        "id": str(row.id),
        "request_type": row.request_type,
        "status": row.status,
        "version": row.version,
        "genai_orion_panel_ticket_id": row.genai_orion_panel_ticket_id,
        "genai_orion_panel_ticket_url": row.genai_orion_panel_ticket_url,
        "requester_name": row.requester_name,
        "requester_email": row.requester_email,
        "environment": row.environment,
        "department_name": getattr(row, "department_name", None),
        "purpose_text": getattr(row, "purpose_text", None),
        "purpose_code": getattr(row, "purpose_code", None),
        "models": getattr(row, "models", None),
        "max_concurrent_requests": getattr(row, "max_concurrent_requests", None),
        "response_window": getattr(row, "response_window", None),
        "usage_frequency": getattr(row, "usage_frequency", None),
        "litellm_team_id": getattr(row, "litellm_team_id", None),
        "key_alias": getattr(row, "key_alias", None),
        "mcp_server_slug": getattr(row, "mcp_server_slug", None),
        "mcp_server_display_name": getattr(row, "mcp_server_display_name", None),
        "mcp_tool_names": getattr(row, "mcp_tool_names", None),
        "all_tools": getattr(row, "all_tools", None),
        "registry_allows_all_tools": getattr(row, "registry_allows_all_tools", None),
        "reject_reason": getattr(row, "reject_reason", None),
        "error_message": getattr(row, "error_message", None),
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else "",
        "completed_at": row.completed_at.isoformat() if getattr(row, "completed_at", None) else "",
    }


async def _load_latest_revision_snapshot(
    session: AsyncSession, request_id: uuid.UUID,
) -> dict[str, object] | None:
    """Revize öncesi client-facing snapshot; yoksa None (sonuç mailinde diff yok)."""
    from sqlalchemy import select

    from ...data.db.models.request_revisions import RequestRevision

    row = await session.scalar(
        select(RequestRevision)
        .where(RequestRevision.request_id == request_id)
        .order_by(RequestRevision.version.desc())
        .limit(1)
    )
    if row is None:
        return None
    raw = row.snapshot
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("revision snapshot JSON değil: request_id=%s", request_id)
        return None
    return parsed if isinstance(parsed, dict) else None


async def _load_approver_emails(session: AsyncSession) -> list[str]:
    from sqlalchemy import select

    from ...data.db.models.config_approvers import ConfigApprover

    rows = await session.scalars(
        select(ConfigApprover.email)
        .where(
            ConfigApprover.scope == "GENAI_APPROVAL",
            ConfigApprover.is_active.is_(True),
        )
        .order_by(ConfigApprover.sort_order.asc())
    )
    return list(rows.all())

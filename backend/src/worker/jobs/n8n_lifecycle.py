"""Sonuç maili sonrası n8n lifecycle webhook job."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.n8n.lifecycle import (
    lifecycle_status,
    n8n_action_for_result_status,
    post_n8n_lifecycle,
)
from backend.src.data.db.models.outbox_jobs import OutboxJob
from backend.src.domain.enums import OutboxJobType
from backend.src.worker.errors import PermanentError, RetryHeld
from backend.src.worker.jobs.common import _load_request, _require_uuid

logger = logging.getLogger(__name__)

_N8N_REQUEST_TYPES = frozenset({"litellm_key", "mcp_key", "mcp_server_registry"})


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def enqueue_notify_n8n_lifecycle(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    action: str,
    ticket_id: str,
) -> None:
    """Sonuç maili gittiğinde n8n job'ı yaz. Aynı request için tek satır."""
    job_type = OutboxJobType.NOTIFY_N8N_LIFECYCLE.value
    payload = {
        "job_type": job_type,
        "request_id": str(request_id),
        "action": action,
        "jira_issue_key": ticket_id,
        "schema_version": 1,
    }
    job = OutboxJob(
        id=uuid.uuid4(),
        job_type=job_type,
        aggregate_type="request",
        aggregate_id=request_id,
        payload=json.dumps(payload),
        dedupe_key=f"n8n_lifecycle:{request_id}:v1",
        status="pending",
        attempts=0,
        max_attempts=5,
        available_at=_utcnow(),
    )
    try:
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError:
        logger.info("n8n lifecycle already queued for %s", request_id)


async def enqueue_n8n_after_result_mail(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    request: dict,
) -> None:
    """completed → approved, rejected → rejected. Diğer status / tip atlanır."""
    request_type = str(request.get("request_type") or "")
    if request_type not in _N8N_REQUEST_TYPES:
        return
    action = n8n_action_for_result_status(str(request.get("status") or ""))
    ticket = str(request.get("genai_orion_panel_ticket_id") or "").strip()
    if not action or not ticket:
        return
    await enqueue_notify_n8n_lifecycle(
        session, request_id=request_id, action=action, ticket_id=ticket,
    )


async def handle_notify_n8n_lifecycle(
    *,
    session: AsyncSession,
    payload: dict,
) -> None:
    """Payload: ``{request_id, action, jira_issue_key, schema_version}``."""
    request_id = _require_uuid(payload, "request_id")
    request = await _load_request(session, request_id)
    if request is None:
        raise PermanentError(f"request bulunamadı: {request_id}")

    ticket = (
        str(request.get("genai_orion_panel_ticket_id") or "").strip()
        or str(payload.get("jira_issue_key") or "").strip()
    )
    action = str(payload.get("action") or "").strip()
    try:
        response = await post_n8n_lifecycle(jira_issue_key=ticket, action=action)
    except ValueError as exc:
        raise PermanentError(str(exc)) from exc
    except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
        logger.error("n8n lifecycle unreachable: %s", exc)
        raise RetryHeld(f"n8n unavailable: {exc}") from exc

    if response is None:
        return

    snippet = (response.text or "")[:500]
    if response.status_code in {429, 502, 503, 504}:
        raise RetryHeld(f"n8n http {response.status_code}: {snippet}")
    if response.status_code >= 400:
        raise PermanentError(f"n8n http {response.status_code}: {snippet}")

    logger.info(
        "n8n lifecycle notified",
        extra={
            "request_id": str(request_id),
            "ticket": ticket,
            "status": lifecycle_status(action),
        },
    )


__all__ = [
    "enqueue_n8n_after_result_mail",
    "enqueue_notify_n8n_lifecycle",
    "handle_notify_n8n_lifecycle",
]

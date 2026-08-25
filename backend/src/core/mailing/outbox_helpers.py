"""Outbox helpers — receive handler'ı + dead-letter notifier için tek nokta.

Modül `genai_orion_panel_core.application.commands` veya
`genai_orion_panel_api` çağrı zincirlerine katılmaz; stand-alone şekilde
`src.data.db` katmanıyla çalışır. Editable-broken paketlerin yükü
bu modüle girmez.

Public API:
- ``enqueue_approval_request_mail(session, *, request_id, request_type,
   recipient, viewer_base, token)``
- ``enqueue_litellm_down_notice(session, *, recipients, request_id,
   error_code, error_message)``

Her helper tek satırlık outbox INSERT'i yapar; transaction caller'a
bırakılmıştır.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from ...data.db.models.outbox_jobs import OutboxJob
from ...data.db.repository import OutboxRepository
from ...worker.handlers import (
    JOB_TYPE_APPROVAL_MAIL,
    JOB_TYPE_LITELLM_DOWN_NOTICE,
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def enqueue_approval_request_mail(
    session: AsyncSession,
    *,
    request_id: uuid.UUID | str,
    request_type: str,
    recipient: str,
    viewer_base: str = "http://localhost:3000/actions",
    token: str = "",
    required_action: str = "approve",
    created_by: str = "anonymous",
) -> OutboxJob:
    """Approver mail job'ını outbox'a yaz.

    `request_type` (`litellm_key` | `mcp_key`); `recipient` approver list
    başlangıç bilgisi (`Step 3` JWT üretimi için IP); `required_action`
    mail template'inin linklediği eylem (``approve``/``revise``/``reject``).

    Dedup key: ``approval_mail:<request_id>:v1`` — aynı request için birden
    fazla kez enqueue etmekten korur.
    """
    request_id_str = str(request_id)
    repo = OutboxRepository(session)
    job = OutboxJob(
        id=uuid.uuid4(),
        job_type=JOB_TYPE_APPROVAL_MAIL,
        aggregate_id=uuid.UUID(request_id_str),
        payload=json.dumps({
            "schema_version": 1,
            "request_id": request_id_str,
            "request_type": request_type,
            "action": required_action,
            "recipient": recipient,
            "viewer_base": viewer_base,
            "token": token,
            "created_by": created_by,
        }),
        dedupe_key=f"approval_mail:{request_id_str}:v1",
        status="pending",
        available_at=_utcnow(),
        attempts=0,
        max_attempts=5,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    return await repo.insert(job)


async def enqueue_litellm_down_notice(
    session: AsyncSession,
    *,
    recipients: Iterable[str],
    request_id: uuid.UUID | str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> OutboxJob:
    """Dead-letter tarafından approver'lara bildirim maili olarak
    gönderilecek job.

    Worker dispatcher bu job'ı claim ederken `core.mailing.mailer.send_mail`
    üzerinden doğrudan SMTP çağrısı yapar — outbox'a düşmesi tek
    pattern'da retry/backoff almak için. Handler içinde başka bir outbox
    INSERT yapılmaz (sonsuz loop riski).

    Dedup key: ``litellm_down:<request_id or "global">:<error_code>:v1``.
    """
    recipients = list(recipients)
    if not recipients:
        msg = "recipients boş; litellm_down mail enqueue edilmedi"
        raise ValueError(msg)
    if not error_code:
        error_code = "LITELLM_DOWN"
    sketch = ",".join(recipients[:3])
    repo = OutboxRepository(session)
    job = OutboxJob(
        id=uuid.uuid4(),
        job_type=JOB_TYPE_LITELLM_DOWN_NOTICE,
        aggregate_id=(
            uuid.UUID(str(request_id)) if request_id else uuid.uuid4()
        ),
        payload=json.dumps({
            "schema_version": 1,
            "recipients": recipients,
            "request_id": str(request_id) if request_id else None,
            "error_code": error_code,
            "error_message": (error_message or "")[:2000],
            "sketch": sketch,
        }),
        dedupe_key=(
            f"litellm_down:"
            f"{str(request_id) if request_id else 'global'}:"
            f"{error_code}:v1"
        ),
        status="pending",
        available_at=_utcnow(),
        attempts=0,
        max_attempts=3,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    return await repo.insert(job)


__all__ = [
    "enqueue_approval_request_mail",
    "enqueue_litellm_down_notice",
]

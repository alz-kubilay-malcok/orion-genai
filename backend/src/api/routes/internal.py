"""POST /internal/chatbot/{request_id}/complete (Bölüm 4.3).

- Approval token kullanmaz; service credential ile authenticate
  (LDAP'a taşınınca buraya bir auth middleware eklenecek; boot sırasında
  ``Settings.BACKEND_SERVICE_TOKEN`` env ya da peer-IP allowlist).
- Assigned request'i optimistic version ile completed yapar.
- Audit + result mail job'u atomik yazılır.
- Attachment backend'e taşınmaz.

Refactor (2026-08-25): ``UnitOfWork`` soyutlaması bypass edilip doğrudan
ORM ``Request`` ile çalışılıyor. ``req.apply_status`` bağımlılığı sıfır.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request as FastAPIRequest
from fastapi.responses import JSONResponse
from sqlalchemy import select

from backend.src.data.db.models.audit_events import AuditEvent
from backend.src.data.db.models.outbox_jobs import OutboxJob
from backend.src.data.db.models.requests import Request
from backend.src.domain.enums import OutboxJobType, RequestStatus, is_terminal

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["internal"])


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.post("/chatbot/{request_id}/complete")
async def complete_chatbot_request(
    request: FastAPIRequest, request_id: str,
) -> JSONResponse:
    """Service-authenticated chatbot completion endpoint (Bölüm 4.3, Bölüm 10.3).

    Davranış:
    * Talep bulunmazsa 404 ``NOT_FOUND``.
    * Status terminallerdense veya ``ASSIGNED`` değilse idempotent
      no-op → mevcut status response ile.
    * Aksi halde: status=COMPLETED, completed_at=now, version+=1, audit
      + ``outbox_jobs`` ile ``SEND_RESULT_MAIL`` job'ı tek transaction.
    """
    state: AppState = request.app.state.container

    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError:
        return JSONResponse(
            status_code=400, content={"error_code": "INVALID_REQUEST_ID"},
        )

    async with state.session_factory() as session:
        stmt = (
            select(Request)
            .where(Request.id == request_uuid)
            .with_for_update()
        )
        req = (await session.execute(stmt)).scalar_one_or_none()
        if req is None:
            return JSONResponse(
                status_code=404, content={"error_code": "NOT_FOUND"},
            )

        if is_terminal(req.status) or req.status != RequestStatus.ASSIGNED.value:
            return JSONResponse(
                content={"request_id": str(req.id), "status": req.status},
            )

        now = _utcnow()
        req.status = RequestStatus.COMPLETED.value
        req.completed_at = now
        req.updated_at = now
        req.version = req.version + 1

        # Audit row.
        session.add(
            AuditEvent(
                id=uuid.uuid4(),
                request_id=req.id,
                event_type="chatbot_completed",
                actor_type="internal_service",
                actor_id=None,
                request_version=req.version,
                metadata_json=json.dumps({"request_version": req.version}),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
        )

        # Outbox: send_result_mail job.
        session.add(
            OutboxJob(
                id=uuid.uuid4(),
                job_type=OutboxJobType.SEND_RESULT_MAIL.value,
                aggregate_type="request",
                aggregate_id=req.id,
                payload=json.dumps({
                    "job_type": OutboxJobType.SEND_RESULT_MAIL.value,
                    "request_id": str(req.id),
                    "schema_version": 1,
                }),
                dedupe_key=f"send_result_mail:{req.id}:v1",
                status="pending",
                attempts=0,
                max_attempts=5,
                available_at=now,
            )
        )

        await session.commit()

    return JSONResponse(
        content={"request_id": str(req.id), "status": req.status},
    )

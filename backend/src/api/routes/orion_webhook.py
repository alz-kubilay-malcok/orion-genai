"""`POST /webhooks/orion` — HMAC, validate, persist, approver outbox."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select

from ...core.mailing.outbox_helpers import enqueue_approval_request_mail
from ...data.db.models.config_approvers import ConfigApprover
from ...data.db.models.requests import Request as RequestModel
from ...data.db.repository import RequestRepository
from ...observability.events import log_event
from ..utils.action_tokens import compact_of, issue_tokens_for_request
from ..utils.schemas.webhook import SCHEMA_BY_TALEP_TURU
from ..utils.webhook_mapping import payload_to_request_fields, resolve_request_type

logger = logging.getLogger(__name__)

router = APIRouter(tags=["orion-webhook"])


async def _approver_recipients(session) -> list[str]:
    rows = await session.scalars(
        select(ConfigApprover.email)
        .where(
            ConfigApprover.scope == "GENAI_APPROVAL",
            ConfigApprover.is_active.is_(True),
        )
        .order_by(ConfigApprover.sort_order.asc())
    )
    return list(rows.all())


def _action_base() -> str:
    return os.getenv("PUBLIC_ACTION_BASE_URL", "http://localhost:8056/approvals").rstrip("/")


def webhook_signature_failure(request: Request, body: bytes) -> JSONResponse | None:
    """HMAC-SHA256 over raw body. Empty secret or AUTH_MODE=off → skip (local smoke)."""
    mode = os.getenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac").strip().lower()
    secret = os.getenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", "").strip()
    if mode in {"off", "none", "disabled"} or not secret:
        return None
    provided = (
        request.headers.get("x-genai-orion-panel-signature")
        or request.headers.get("X-GenAi-Orion-Panel-Signature")
        or ""
    ).strip()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if provided and hmac.compare_digest(provided.lower(), expected.lower()):
        return None
    log_event(
        logger, "orion.webhook.invalid",
        level=logging.WARNING,
        error_code="INVALID_WEBHOOK_SIGNATURE",
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error_code": "INVALID_WEBHOOK_SIGNATURE"},
    )


@router.post("/orion", status_code=status.HTTP_202_ACCEPTED)
async def receive_orion_webhook(
    request: Request,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-Id")] = None,
) -> JSONResponse:
    state = request.app.state.container
    factory = state.session_factory

    body = await request.body()
    rejected = webhook_signature_failure(request, body)
    if rejected is not None:
        return rejected

    try:
        raw = json.loads(body) if body else None
    except Exception:  # noqa: BLE001
        log_event(
            logger, "orion.webhook.parse_failed",
            level=logging.WARNING,
            raw_size=str(request.headers.get("content-length") or "?"),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "BAD_JSON", "field_errors": []},
        )

    raw_size_hint = request.headers.get("content-length") or "?"
    log_event(
        logger,
        "orion.webhook.received",
        method="POST",
        path="/webhooks/orion",
        raw_size=str(raw_size_hint),
        ticket_no=str(raw.get("talep_no", "?")) if isinstance(raw, dict) else "?",
    )

    talep_turu = raw.get("talep_turu") if isinstance(raw, dict) else None
    if talep_turu not in SCHEMA_BY_TALEP_TURU:
        log_event(
            logger, "orion.webhook.invalid",
            level=logging.WARNING,
            error_code="UNKNOWN_REQUEST_TYPE",
            talep_turu=str(talep_turu),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "UNKNOWN_REQUEST_TYPE", "field_errors": []},
        )

    schema_cls = SCHEMA_BY_TALEP_TURU[talep_turu]
    try:
        payload = schema_cls.model_validate(raw)
    except ValidationError as exc:
        log_event(
            logger, "orion.webhook.invalid",
            level=logging.WARNING,
            error_code="VALIDATION_ERROR",
            talep_turu=talep_turu,
            field_count=len(exc.errors()),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "VALIDATION_ERROR",
                     "field_errors": exc.errors()},
        )

    try:
        request_type = resolve_request_type(talep_turu)
    except ValueError as exc:
        log_event(
            logger, "orion.webhook.invalid",
            level=logging.WARNING,
            error_code="UNKNOWN_REQUEST_TYPE",
            exc_msg=str(exc),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "UNKNOWN_REQUEST_TYPE",
                     "field_errors": [str(exc)]},
        )

    async with factory() as session:
        repo = RequestRepository(session)
        existing = await repo.get_by_ticket_id(
            ticket_id=payload.talep_no,
            request_type=request_type,
        )
        if existing is not None:
            log_event(
                logger, "orion.webhook.duplicate",
                request_id=str(existing.id),
                ticket_no=payload.talep_no,
                request_type=request_type,
                status=existing.status,
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "request_id": str(existing.id),
                    "status": existing.status,
                    "duplicate": True,
                },
                headers={"X-Correlation-Id": x_correlation_id or ""},
            )

        request_fields = payload_to_request_fields(
            payload, request_type=request_type, raw=raw,
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        request_fields.setdefault("id", uuid4())
        request_fields.setdefault("created_at", now)
        request_fields.setdefault("updated_at", now)
        new_db_request = RequestModel(**request_fields)
        await repo.save(new_db_request)
        await session.flush()

        token_rows = issue_tokens_for_request(
            state.token_signer,
            request_id=new_db_request.id,
            request_type=request_type,
            ttl_hours=state.settings.action_token_ttl_hours,
        )
        action_urls: dict[str, str] = {}
        base = _action_base()
        for token_row in token_rows:
            session.add(token_row)
            compact = compact_of(token_row)
            if compact:
                action_urls[token_row.action] = f"{base}/{quote(compact, safe='.-_')}"

        recipients = await _approver_recipients(session)
        enqueued = 0
        for recipient in recipients:
            await enqueue_approval_request_mail(
                session,
                request_id=new_db_request.id,
                request_type=request_type,
                recipient=recipient,
                viewer_base=base,
                token=compact_of(token_rows[0]) if token_rows else "",
                required_action="approve",
                created_by=payload.talep_eden_eposta,
                action_urls=action_urls,
            )
            enqueued += 1

        await session.commit()

    log_event(
        logger, "orion.webhook.accepted",
        request_id=str(new_db_request.id),
        ticket_no=payload.talep_no,
        request_type=request_type,
        approver_mails_enqueued=enqueued,
        requester_email=payload.talep_eden_eposta,
    )
    response: dict[str, Any] = {
        "request_id": str(new_db_request.id),
        "status": "waiting_approval",
        "approver_mails_enqueued": enqueued,
    }
    if not recipients:
        logger.warning(
            "approver listesi boş; outbox'a mail düşmedi",
            extra={"event": "orion.webhook.no_approvers",
                   "request_id": str(new_db_request.id),
                   "request_type": request_type},
        )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response,
        headers={"X-Correlation-Id": x_correlation_id or ""},
    )


__all__ = ["receive_orion_webhook", "router", "webhook_signature_failure"]

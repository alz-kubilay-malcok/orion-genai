"""Outbox mail jobs."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import WorkerDependencies
from ..errors import PermanentError, RetryHeld
from .common import (
    _decrypt_request_secret,
    _load_latest_revision_snapshot,
    _load_request,
    _require_uuid,
)

logger = logging.getLogger(__name__)

async def handle_send_result_mail(
    *,
    session: AsyncSession,
    payload: dict,
    deps: WorkerDependencies | None = None,
    api_key: str = "",
) -> None:
    """Talep sonuç mailini talep sahibine atar.

    Payload: `{request_id, job_type, schema_version}`.
    `requests` tablosundan detaylar okunur; status türe göre template seçilir.
    Plaintext key outbox'ta yok; varsa `secrets` satırından decrypt edilir.
    """
    request_id = _require_uuid(payload, "request_id")
    from ...core.mailing.mailer import send_mail
    from ...core.mailing.result_inputs import (
        litellm_result_inputs,
        mcp_result_inputs,
        result_template_name,
    )
    request = await _load_request(session, request_id)
    if request is None:
        msg = f"request bulunamadı: {request_id}"
        raise PermanentError(msg)

    api_key = (api_key or "").strip()
    if not api_key:
        api_key = await _decrypt_request_secret(
            session, request_id=request_id, cipher=getattr(deps, "secret_cipher", None),
        )
    template = result_template_name(str(request["request_type"]))
    if request["request_type"] == "litellm_key":
        revision_before = await _load_latest_revision_snapshot(session, request_id)
        inputs = litellm_result_inputs(
            request, revision_before=revision_before, api_key=api_key,
        )
    else:
        inputs = mcp_result_inputs(request, api_key=api_key)
    subject = f"[GenAi] {request['genai_orion_panel_ticket_id']} — sonuç"
    try:
        ok = send_mail(
            recipients=[request["requester_email"]],
            subject=subject,
            template_name=template,
            inputs=inputs,
        )
    except FileNotFoundError as exc:
        raise PermanentError(str(exc)) from exc
    except Exception as exc:
        msg = f"smtp send failed: {exc}"
        raise RetryHeld(msg) from exc
    if not ok:
        msg = "mailer False döndü"
        raise RetryHeld(msg)
    logger.info(
        "send_result_mail: delivered",
        extra={"request_id": str(request_id), "to": request["requester_email"]},
    )
    from .n8n_lifecycle import enqueue_n8n_after_result_mail

    await enqueue_n8n_after_result_mail(
        session, request_id=request_id, request=request,
    )


async def _handle_send_approval_mail(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    """Send one approval mail to the payload recipient using HMAC action URLs."""
    from ...core.mailing.mailer import send_mail

    request_id = _require_uuid(payload, "request_id")
    recipient = str(payload.get("recipient") or "").strip()
    if not recipient:
        msg = "approval mail payload'unda recipient eksik"
        raise PermanentError(msg)

    request = await _load_request(session, request_id)
    if request is None:
        msg = f"request bulunamadı: {request_id}"
        raise PermanentError(msg)

    action_urls = payload.get("action_urls") or {}
    token = str(payload.get("token") or "")
    viewer_base = str(payload.get("viewer_base") or "http://localhost:8056/approvals").rstrip("/")
    approve_link = action_urls.get("approve") or (f"{viewer_base}/{token}" if token else "")
    reject_link = action_urls.get("reject") or approve_link
    revise_link = action_urls.get("revise") or ""

    from ...core.mailing.approval_inputs import litellm_approval_inputs, mcp_approval_inputs

    is_mcp = request["request_type"] in {"mcp_key", "mcp_server_registry"}
    template = "mcp_key_approval" if is_mcp else "litellm_key_approval"
    inputs: dict[str, object]
    if is_mcp:
        inputs = mcp_approval_inputs(
            request,
            recipient=recipient,
            approve_link=approve_link,
            reject_link=reject_link,
        )
    else:
        inputs = dict(
            litellm_approval_inputs(
                request,
                recipient=recipient,
                approve_link=approve_link,
                reject_link=reject_link,
                revise_link=revise_link,
            )
        )
    try:
        ok = send_mail(
            recipients=[recipient],
            subject=f"[GenAi] {request['genai_orion_panel_ticket_id']} — onayınız bekleniyor",
            template_name=template,
            inputs=inputs,
        )
    except Exception as exc:
        msg = f"smtp send failed: {exc}"
        raise RetryHeld(msg) from exc
    if not ok:
        msg = "mailer False döndü"
        raise RetryHeld(msg)
    logger.info(
        "send_approval_mail: delivered",
        extra={"request_id": str(request_id), "to": recipient},
    )


async def _handle_send_litellm_down_notice(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    from ...core.mailing.mailer import send_mail

    recipients = list(payload.get("recipients") or [])
    if not recipients:
        msg = "litellm_down_notice recipients boş"
        raise PermanentError(msg)
    message = (
        payload.get("error_message")
        or payload.get("error_code")
        or "provisioning provider unavailable"
    )
    try:
        ok = send_mail(
            recipients=recipients,
            subject="[GenAi] provision/LiteLLM uyarısı",
            message=str(message),
        )
    except Exception as exc:
        msg = f"smtp send failed: {exc}"
        raise RetryHeld(msg) from exc
    if not ok:
        raise RetryHeld("mailer False döndü")
    logger.info("send_litellm_down_notice: delivered", extra={"to": recipients})


"""Worker outbox handler facade'leri.

Handler sözleşmesi: ``async def handle(*, session, payload) -> None``.
Success → exception yok; Failure → `WorkerError` alt sınıfı raise eder.

Handler dispatch edilirken dispatcher transaction'a girmez; handler'lar
kendi iç transaction sınırlarını kendileri yönetir (provision handler'ları
`run_provision_job` üzerinden kendi UoW'unu açar).

`OUTBOX_HANDLERS` modül-load sırasında boştur; dispatcher her tick'te
`build_handlers(deps)` callable'ı ile per-process handler tablosunu kurup
dispatch sırasında kullanır. Bu sayede adapter yükleme sırası dispatch'tan
ayrılmış olur.
"""

from __future__ import annotations

import logging
import uuid
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import WorkerDependencies
from .errors import PermanentError, RetryHeld

logger = logging.getLogger(__name__)

# Domain enum (`OutboxJobType`) editable-install break yüzünden
# bu turda import edilemiyor (packages/genai-orion-panel-core yolu
# diskte yok). String literal dispatch key'lerini burada
# daraltıyoruz; rationale:
#   - outbox_jobs.job_type TEXT; bu value'lar authoritative.
#   - `genai_orion_panel_core` editable broken; yeni backend bu tur
#     kapsamında reference etmiyoruz. Eski import patch outbox
#     dispatch refactor'u ile merge edilecek.
JOB_TYPE_PROVISION_LITELLM = "provision:litellm_key"
JOB_TYPE_PROVISION_MCP = "provision:mcp_key"
JOB_TYPE_SEND_RESULT_MAIL = "send:result_mail"
JOB_TYPE_REGISTER_MCP = "registry:mcp_server"
JOB_TYPE_APPROVAL_MAIL = "send:approval_mail"
JOB_TYPE_LITELLM_DOWN_NOTICE = "send:litellm_down_notice"


# ---- Closure-bindable HANDLERS -------------------------------------------


def build_handlers(deps: WorkerDependencies) -> dict[str, Callable[..., Awaitable[None]]]:
    """Per-process handler dispatch tablosu — `deps` injection'lı."""
    return {
        JOB_TYPE_PROVISION_LITELLM: _make_provision_litellm_handler(deps),
        JOB_TYPE_PROVISION_MCP: _make_provision_mcp_handler(deps),
        JOB_TYPE_SEND_RESULT_MAIL: handle_send_result_mail,
        JOB_TYPE_REGISTER_MCP: handle_register_mcp,
        JOB_TYPE_APPROVAL_MAIL: _make_send_approval_mail_handler(deps),
        JOB_TYPE_LITELLM_DOWN_NOTICE: _make_send_litellm_down_notice_handler(deps),
    }


def _make_provision_litellm_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_provision_litellm(session=session, deps=deps, payload=payload)
    return handler


def _make_provision_mcp_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_provision_mcp(session=session, deps=deps, payload=payload)
    return handler


def _make_send_approval_mail_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_send_approval_mail(session=session, deps=deps, payload=payload)
    return handler


def _make_send_litellm_down_notice_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_send_litellm_down_notice(
            session=session, deps=deps, payload=payload,
        )
    return handler


# Salt public yüz: legacy import'lar için. Modül load anında boş tablo;
# dispatcher `build_handlers(deps)` kullanır.
OUTBOX_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {}


# ---- Handlers -----------------------------------------------------------


async def handle_send_result_mail(*, session: AsyncSession, payload: dict) -> None:
    """Talep sonuç mailini talep sahibine atar.

    Payload: `{request_id, job_type, schema_version}`.
    `requests` tablosundan detaylar okunur; status türe göre template seçilir.
    """
    request_id = _require_uuid(payload, "request_id")
    from ..core.mailing.mailer import send_mail
    request = await _load_request(session, request_id)
    if request is None:
        msg = f"request bulunamadı: {request_id}"
        raise PermanentError(msg)

    template, subject_extra = _result_template(request)
    inputs = _build_result_inputs(request, extra=subject_extra)
    try:
        ok = send_mail(
            recipients=[request["requester_email"]],
            subject=subject_extra["subject"],
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
        "send_result_mail: delivered",
        extra={"request_id": str(request_id), "to": request["requester_email"]},
    )


async def _handle_send_approval_mail(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    """Approver listesi (`config_approvers`'ten) çekilip JWT capability
    maili atılır.

    Payload alanları: `{request_id, action, token, viewer_base}`.
    `token` adım 3'te `core.mailing.jwt_mail.issue(...)` tarafından üretilecek;
    şu an payload üzerinden client-side kabul ediyoruz.
    """
    from ..core.mailing.mailer import send_mail

    request_id = _require_uuid(payload, "request_id")
    action = payload.get("action")
    if action not in {"approve", "revise", "reject"}:
        msg = f"bilinmeyen approval action: {action!r}"
        raise PermanentError(msg)

    approver_emails = await _load_approver_emails(session)
    if not approver_emails:
        msg = "config_approvers(scope=GENAI_APPROVAL) boş; mail atılmadı"
        raise PermanentError(msg)

    request = await _load_request(session, request_id)
    if request is None:
        msg = f"request bulunamadı: {request_id}"
        raise PermanentError(msg)

    viewer_base = payload.get("viewer_base") or "http://localhost:3000/actions"

    # Step 3: JWT capability token üret — `approval_token_issuer` deps'te
    # bağlı ise payload'daki (place-holder olabilen) `token` alanını
    # yenisiyle doldur. Üretilecek token `request_type/request_id/recipient`
    # claim'leriyle tek-kullanım JWT'dir.
    request_type = request.get("request_type") or "litellm_key"
    request_recipient = payload.get("recipient") or \
        (request.get("requester_email") or "anon@local")
    if deps.approval_token_issuer is not None:
        issued = deps.approval_token_issuer(
            request_id=str(request_id),
            request_type=request_type,
            action=action,
            recipient=request_recipient,
        )
        token = getattr(issued, "compact_token", str(issued))
    else:
        token = str(payload.get("token") or "")
        if not token:
            msg = "approval mail payload'unda 'token' eksik (approval_token_issuer deps'te yok)"
            raise PermanentError(msg)

    if not token:
        msg = "approval token üretilemedi"
        raise PermanentError(msg)

    inputs = {
        "approver_list_count": len(approver_emails),
        "ticket_id": request["genai_orion_panel_ticket_id"],
        "ticket_url": request["genai_orion_panel_ticket_url"],
        "requester_name": request["requester_name"],
        "action": action,
        "action_url": f"{viewer_base}/{token}/{action}",
    }
    try:
        ok = send_mail(
            recipients=approver_emails,
            subject=f"[GenAi] {request['genai_orion_panel_ticket_id']} — onayınız bekleniyor",
            template_name="litellm_key_approval",
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
        extra={"request_id": str(request_id), "to": approver_emails, "action": action},
    )


async def handle_register_mcp(*, session: AsyncSession, payload: dict) -> None:
    """`REGISTER_MCP_SERVER` artık pipeline dışı.

    Kullanıcı kararı: register talebi geldiğinde handler-side yapacak
    işlem yok; sadece doğrulama ve bilgilendirme çıktısı yeterli. Bu job
    pipeline'ı kirletmesin diye hemen 'completed' etmek üzere no-op.
    """
    logger.info(
        "register_mcp_server: pipeline dışı — completed",
        extra={"request_id": payload.get("request_id")},
    )


# ---- Provision handler'ları (deps injection'lı) -------------------------


async def _handle_provision_litellm(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    """LiteLLM key provizyonu. Adapter DI factory'den gelen `litellm` port'unu kullanır.

    Geçici provider hataları RetryHeld'a yeniden paketlenir; kalıcı hatalar
    PermanentError. Adapter injection eksikse explicit PermanentError.
    """
    if deps.litellm is None:
        msg = "LITELLM_BASE_URL set ama adapter paketi (genai_orion_panel_adapters.litellm) yok; provisioning devre dışı"
        raise PermanentError(msg)
    try:
        await _run_provision_job(deps=deps, payload=payload)
    except ValueError as exc:
        msg = f"provision permanent error: {exc}"
        raise PermanentError(msg) from exc
    except (ConnectionError, TimeoutError, OSError) as exc:
        msg = f"litellm outage: {exc}"
        raise RetryHeld(msg) from exc
    except Exception as exc:  # noqa: BLE001 — surface other transient failure modes
        msg = f"litellm transient failure: {exc!r}"
        raise RetryHeld(msg) from exc


async def _handle_provision_mcp(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    """MCP scoped key provision. `mcp_provision` port factory'den."""
    if deps.mcp_provision is None:
        msg = "MCP gateway adapter yok; provisioning devre dışı"
        raise PermanentError(msg)
    try:
        await _run_provision_job(deps=deps, payload=payload)
    except ValueError as exc:
        msg = f"provision permanent error: {exc}"
        raise PermanentError(msg) from exc
    except (ConnectionError, TimeoutError, OSError) as exc:
        msg = f"mcp gateway outage: {exc}"
        raise RetryHeld(msg) from exc


async def _run_provision_job(*, deps: WorkerDependencies, payload: dict) -> None:
    """Adapter `run_provision_job` core paketinde; o broken şu an.

    Bu turda adapter import olsa bile dispatch contract'ı sağlamak için
    inline-dispatch yapıyoruz: payload'daki job_type işaretini okuyup
    uygun provizyonu koşuyoruz. Core paket geri geldiğinde bu helper
    yerine `from genai_orion_panel_core...` import'u takılacak.
    """
    job_type_value = payload.get("job_type")
    if job_type_value == JOB_TYPE_PROVISION_LITELLM:
        logger.info("litellm provision: payload=%s", payload)
        return
    if job_type_value == JOB_TYPE_PROVISION_MCP:
        logger.info("mcp provision: payload=%s", payload)
        return
    msg = f"Bilinmeyen provision job_type: {job_type_value!r}"
    raise ValueError(msg)


# ---- Helpers ------------------------------------------------------------


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

    from ..data.db.models.requests import Request

    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is None:
        return None
    return {
        "id": str(row.id),
        "request_type": row.request_type,
        "status": row.status,
        "genai_orion_panel_ticket_id": row.genai_orion_panel_ticket_id,
        "genai_orion_panel_ticket_url": row.genai_orion_panel_ticket_url,
        "requester_name": row.requester_name,
        "requester_email": row.requester_email,
        "environment": row.environment,
        "purpose_text": getattr(row, "purpose_text", None),
    }


async def _load_approver_emails(session: AsyncSession) -> list[str]:
    from sqlalchemy import select

    from ..data.db.models.config_approvers import ConfigApprover

    rows = await session.scalars(
        select(ConfigApprover.email)
        .where(
            ConfigApprover.scope == "GENAI_APPROVAL",
            ConfigApprover.is_active.is_(True),
        )
        .order_by(ConfigApprover.sort_order.asc())
    )
    return list(rows.all())


def _result_template(request: dict) -> tuple[str, dict]:
    """Talep türüne göre (template_adı, subject_helpers) çiftini döndürür."""
    rt = request["request_type"]
    subject = f"[GenAi] {request['genai_orion_panel_ticket_id']} — sonuç"
    base = {"subject": subject}
    if rt in {"litellm_key", "mcp_key"}:
        return "request_result", base
    return "request_result_generic", base


def _build_result_inputs(request: dict, *, extra: dict) -> dict[str, object]:
    return {
        "requester_name": request["requester_name"],
        "ticket_id": request["genai_orion_panel_ticket_id"],
        "ticket_url": request["genai_orion_panel_ticket_url"],
        "request_type": request["request_type"],
        "status": request["status"],
        "purpose_text": request.get("purpose_text"),
        **extra,
    }


# --- Dead-letter approver-mail handler -----------------------------------------

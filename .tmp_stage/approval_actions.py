"""Admin approval action route'ları (Bölüm 10.3, Bölüm 11).

- GET  /actions?t=...   → confirmation form (side effect yok).
- POST /actions/approve|revise|reject → tek transaction; first-POST-wins.
- Revise yalnız `litellm_key` için geçerlidir (ADR-011).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from genai_orion_panel_core.application.commands.approve_request import (
    ApproveRequestCommand,
    ApproveRequestHandler,
)
from genai_orion_panel_core.application.commands.reject_request import (
    RejectRequestCommand,
    RejectRequestHandler,
)
from genai_orion_panel_core.application.commands.revise_request import (
    ReviseRequestCommand,
    ReviseRequestHandler,
)
from genai_orion_panel_core.domain.enums import ApprovalAction
from genai_orion_panel_core.domain.errors import DomainError

from dataclasses import asdict

from genai_orion_panel_api.schemas.actions import (
    ApprovalViewModel,
    PostApproveBody,
    PostRejectBody,
    PostReviseBody,
)

if TYPE_CHECKING:
    from genai_orion_panel_api.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-actions"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_TEMPLATE_BY_ACTION = {
    ApprovalAction.APPROVE: "approve.html",
    ApprovalAction.REVISE: "revise.html",
    ApprovalAction.REJECT: "reject.html",
}

_DOMAIN_ERROR_STATUS = {
    "INVALID_ACTION_TOKEN": 401,
    "ACTION_NOT_ALLOWED_FOR_TYPE": 409,
    "ALREADY_PROCESSED": 200,
    "OPTIMISTIC_LOCK_CONFLICT": 409,
}


def _wants_html(request: Request) -> bool:
    """Outlook/JS'siz form POST'u algılar: form-encoded body -> HTML sonuç sayfası."""
    content_type = request.headers.get("content-type", "")
    return "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type


async def _read_body(request: Request) -> dict:
    if _wants_html(request):
        form = await request.form()
        return dict(form)
    return await request.json()


def _result_response(request: Request, *, status_value: str, message: str) -> HTMLResponse | JSONResponse:
    if _wants_html(request):
        return _templates.TemplateResponse(
            request, "action_result.html", {"status": status_value, "message": message}
        )
    return JSONResponse(content={"status": status_value, "message": message})


@router.get("")
async def get_confirmation(request: Request, t: str = Query(...)) -> HTMLResponse:
    """Token validate, status/type/action-aware confirmation form döner (side effect yok)."""
    state: AppState = request.app.state.container
    try:
        claims = state.token_signer.verify(t)
    except DomainError:
        return _templates.TemplateResponse(
            request, "action_result.html", {"status": "invalid", "message": "Token geçersiz veya süresi dolmuş."}
        )

    action = ApprovalAction(claims["action"])
    template_name = _TEMPLATE_BY_ACTION[action]

    async with state.new_uow() as uow:
        from uuid import UUID

        req = await uow.requests.get_by_id(UUID(claims["request_id"]))
        await uow.rollback()

    if req is None:
        return _templates.TemplateResponse(
            request, "action_result.html", {"status": "invalid", "message": "Talep bulunamadı."}
        )

    return _templates.TemplateResponse(
        request,
        template_name,
        {
            "request": req,
            "request_type": req.request_type,
            "token": t,
            "request_version": req.version,
        },
    )


@router.get("/{token}/view", response_model=ApprovalViewModel)
async def get_action_view(request: Request, token: str) -> JSONResponse | ApprovalViewModel:
    """JSON view — Next.js viewer frontend için read-only snapshot (side effect yok)."""
    state: AppState = request.app.state.container
    try:
        claims = state.token_signer.verify(token)
    except DomainError:
        return JSONResponse(status_code=401, content={"error_code": "INVALID_ACTION_TOKEN"})

    action = ApprovalAction(claims["action"])

    async with state.new_uow() as uow:
        from uuid import UUID

        req = await uow.requests.get_by_id(UUID(claims["request_id"]))
        await uow.rollback()

    if req is None:
        return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})

    detail = asdict(req.detail) if req.detail is not None else {}
    return ApprovalViewModel(
        action=action.value,
        request_id=str(req.id),
        request_type=req.request_type.value,
        status=req.status.value,
        request_version=req.version,
        genai_orion_panel_ticket_id=req.genai_orion_panel_ticket_id,
        genai_orion_panel_ticket_url=req.genai_orion_panel_ticket_url,
        requester_name=req.requester_name,
        requester_email=req.requester_email,
        environment=req.environment.value if req.environment is not None else "",
        created_at=req.genai_orion_panel_created_at,
        detail=detail,
    )


@router.post("/approve", response_model=None)
async def post_approve(request: Request) -> HTMLResponse | JSONResponse:
    """Type'a göre provision/register job enqueue. JSON veya form-encoded body kabul eder."""
    raw = await _read_body(request)
    raw.setdefault("allows_all_tools", None)
    if isinstance(raw.get("allows_all_tools"), str):
        raw["allows_all_tools"] = raw["allows_all_tools"].lower() in ("true", "on", "1", "yes")
    body = PostApproveBody.model_validate(raw)

    state: AppState = request.app.state.container
    handler = ApproveRequestHandler(state.new_uow(), state.token_signer)
    command = ApproveRequestCommand(
        compact_token=body.token,
        token_hash=state.token_signer.hash_token(body.token),
        request_version=body.request_version,
        allows_all_tools=body.allows_all_tools,
        actor_id=None,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    try:
        result = await handler.handle(command)
    except DomainError as exc:
        if _wants_html(request):
            return _result_response(request, status_value=exc.error_code, message="Talep onaylanamadı.")
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    if _wants_html(request):
        return _result_response(
            request, status_value=result.status.value, message="Talep onaylandı; sağlama kuyruğa alındı."
        )
    return JSONResponse(content={"request_id": str(result.request_id), "status": result.status.value})


@router.post("/revise", response_model=None)
async def post_revise(request: Request) -> HTMLResponse | JSONResponse:
    """LiteLLM-only: positive tpm/rpm approved limits persist + provision enqueue.

    Body'de opsiyonel ``models`` / ``response_window`` / ``usage_frequency`` alanları
    requestera bildirilecek client-facing düzeltmelerdir; verilmediğinde alana
    dokunulmaz. Operasyonel ``tpm_approved`` / ``rpm_approved`` zorunludur ve
    requester-facing maillerde gösterilmez.
    """
    raw = await _read_body(request)
    for key in ("request_version", "tpm_approved", "rpm_approved"):
        if key in raw and isinstance(raw[key], str):
            raw[key] = int(raw[key])
    if "models" in raw and isinstance(raw["models"], str):
        # form-encoded body'de liste virgülle gelir; HTML form için basit split.
        raw["models"] = [m for m in (s.strip() for s in raw["models"].split(",")) if m]
    body = PostReviseBody.model_validate(raw)

    state: AppState = request.app.state.container
    handler = ReviseRequestHandler(state.new_uow(), state.token_signer)
    command = ReviseRequestCommand(
        compact_token=body.token,
        token_hash=state.token_signer.hash_token(body.token),
        request_version=body.request_version,
        tpm_approved=body.tpm_approved,
        rpm_approved=body.rpm_approved,
        admin_note=body.admin_note,
        actor_id=None,
        models=body.models,
        response_window=body.response_window,
        usage_frequency=body.usage_frequency,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    try:
        result = await handler.handle(command)
    except DomainError as exc:
        if _wants_html(request):
            return _result_response(request, status_value=exc.error_code, message="Revize gönderilemedi.")
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    if _wants_html(request):
        return _result_response(
            request, status_value=result.status.value, message="Revize kaydedildi; sağlama kuyruğa alındı."
        )
    return JSONResponse(content={"request_id": str(result.request_id), "status": result.status.value})


@router.post("/reject", response_model=None)
async def post_reject(request: Request) -> HTMLResponse | JSONResponse:
    """Tüm automated tiplerde kullanılabilir; reject_reason bounded 1..2000."""
    raw = await _read_body(request)
    if "request_version" in raw and isinstance(raw["request_version"], str):
        raw["request_version"] = int(raw["request_version"])
    body = PostRejectBody.model_validate(raw)

    state: AppState = request.app.state.container
    handler = RejectRequestHandler(state.new_uow(), state.token_signer)
    command = RejectRequestCommand(
        compact_token=body.token,
        token_hash=state.token_signer.hash_token(body.token),
        request_version=body.request_version,
        reject_reason=body.reject_reason,
        actor_id=None,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    try:
        result = await handler.handle(command)
    except DomainError as exc:
        if _wants_html(request):
            return _result_response(request, status_value=exc.error_code, message="Talep reddedilemedi.")
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    if _wants_html(request):
        return _result_response(
            request, status_value=result.status.value, message="Talep reddedildi."
        )
    return JSONResponse(content={"request_id": str(result.request_id), "status": result.status.value})

"""Token-driven approval action route'ları (Bölüm 10.3, Bölüm 11).

- GET  /actions/{token}/view → read-only snapshot (side effect yok).
- POST /actions/approve|revise|reject → JSON tek transaction; first-POST-wins.
- Revise yalnız ``litellm_key`` için geçerlidir (ADR-011).

Refactor (2026-08-25): legacy ``genai_orion_panel_core.application.commands``
import zincirleri sıfırlandı. Bu modül artık ``state.token_signer.verify``
üzerinden claims çıkarır, ardından :mod:`backend.src.api.utils.admin_service`
altındaki ``admin_approve/revise/reject`` fonksiyonlarını çağırır.

Bu yaklaşım admin panel ile single-token arasındaki farkı:
  * admin_service: ``actor_id`` strings (admin username veya token sub) alır,
    tipping-point ``version`` ve ``status`` kontrolleri ``admin_service``
    içinde yapılır.
  * Bu modül: tokeni verify eder, claims'den ``request_id`` + ``version``
    çıkarır, session başlatır, admin_service'i çağırır. Actor olarak
    token kaynağı (mail veya LDAP badge) ``correlation_id`` altında loglanır.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request as FastAPIRequest
from fastapi.responses import JSONResponse
from sqlalchemy import select

from backend.src.api.utils import admin_service
from backend.src.api.utils.action_tokens import (
    consume_winning_token,
    verify_token_against_db,
)
from backend.src.api.utils.schemas.actions import (
    ApprovalViewModel,
    PostApproveBody,
    PostRejectBody,
    PostReviseBody,
)
from backend.src.data.db.models.requests import Request
from backend.src.domain.enums import ApprovalAction
from backend.src.domain.errors import DomainError, InvalidActionTokenError, RequestNotFoundError

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-actions"])

# Map: domain error_code → HTTP status. ``approval_actions`` ve ``admin``
# rotaları aynı kuralları paylaşır (bkz. routes/admin.py::_DOMAIN_ERROR_STATUS).
_DOMAIN_ERROR_STATUS = {
    "INVALID_ACTION_TOKEN": 401,
    "ACTION_NOT_ALLOWED_FOR_TYPE": 409,
    "NOT_FOUND": 404,
    "ALREADY_PROCESSED": 200,
    "OPTIMISTIC_LOCK_CONFLICT": 409,
}


def _row_to_detail_dict(row: Request) -> dict:
    """ORM satırından emanet detail dict'i çıkar (admin.py varyantı ile aynı)."""
    keys = (
        "department_name", "request_description", "purpose_code",
        "use_case", "models", "response_window", "usage_frequency",
        "estimated_daily_requests", "max_concurrent_requests",
        "input_pages", "output_pages", "estimated_tokens_per_request",
        "key_alias", "litellm_team_id",
        "mcp_server_slug", "mcp_tool_names", "all_tools",
        "registry_allows_all_tools",
        "mcp_server_display_name", "project_name", "technical_owner_email",
        "repo_platform", "repo_url", "devops_jira_key",
        "mcp_endpoint_url", "minimum_evaluation_score",
    )
    return {k: getattr(row, k) for k in keys if getattr(row, k) is not None}


@router.get("/{token}/view", response_model=ApprovalViewModel)
async def get_action_view(
    request: FastAPIRequest, token: str,
) -> JSONResponse | ApprovalViewModel:
    """JSON view — viewer frontend için read-only snapshot (side effect yok)."""
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            claims, _row = await verify_token_against_db(
                session, state.token_signer, token,
            )
    except InvalidActionTokenError:
        return JSONResponse(
            status_code=401, content={"error_code": "INVALID_ACTION_TOKEN"},
        )

    try:
        action = ApprovalAction(claims["action"])
    except (KeyError, ValueError):
        return JSONResponse(
            status_code=401, content={"error_code": "INVALID_ACTION_CLAIM"},
        )

    try:
        request_id = UUID(claims["request_id"])
    except (KeyError, ValueError):
        return JSONResponse(
            status_code=401, content={"error_code": "INVALID_REQUEST_ID_CLAIM"},
        )

    async with state.session_factory() as session:
        stmt = select(Request).where(Request.id == request_id)
        req = (await session.execute(stmt)).scalar_one_or_none()

    if req is None:
        raise RequestNotFoundError("talep bulunamadı")

    litellm_teams: list[dict[str, str]] = []
    if req.request_type == "litellm_key" and action.value == "revise":
        from backend.src.core.litellm.generate_key import fetch_litellm_teams

        litellm_teams = await fetch_litellm_teams(req.environment)

    return ApprovalViewModel(
        action=action.value,
        request_id=str(req.id),
        request_type=req.request_type,
        status=req.status,
        request_version=req.version,
        genai_orion_panel_ticket_id=req.genai_orion_panel_ticket_id,
        genai_orion_panel_ticket_url=req.genai_orion_panel_ticket_url,
        requester_name=req.requester_name,
        requester_email=req.requester_email,
        environment=req.environment or "",
        created_at=req.genai_orion_panel_created_at,
        detail=_row_to_detail_dict(req),
        litellm_teams=litellm_teams,
    )


@router.post("/approve", response_model=None)
async def post_approve(request: FastAPIRequest) -> JSONResponse:
    """Type'a göre provision/register job enqueue. JSON body zorunlu."""
    body = PostApproveBody.model_validate(await request.json())

    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            claims, token_row = await verify_token_against_db(
                session, state.token_signer, body.token, expected_action="approve",
            )
            request_id = UUID(claims["request_id"])
            actor_id = f"token:{claims.get('sub', 'mail')}"
            correlation_id = getattr(request.state, "correlation_id", None)
            result = await admin_service.admin_approve(
                session,
                request_id=request_id,
                request_version=body.request_version,
                allows_all_tools=body.allows_all_tools,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            await consume_winning_token(session, token_row)
            await session.commit()
    except (InvalidActionTokenError, KeyError, ValueError) as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get("INVALID_ACTION_TOKEN", 401),
            content={"error_code": "INVALID_ACTION_TOKEN", "detail": str(exc)},
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(
        content={"request_id": str(request_id), "status": result.new_status},
    )


@router.post("/revise", response_model=None)
async def post_revise(request: FastAPIRequest) -> JSONResponse:
    """LiteLLM-only: team_id + max_parallel_requests persist + provision enqueue.

    Body'de opsiyonel ``models`` / ``response_window`` / ``usage_frequency``
    alanları requestera bildirilecek client-facing düzeltmelerdir; verilmediğinde
    alana dokunulmaz.
    """
    body = PostReviseBody.model_validate(await request.json())

    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            claims, token_row = await verify_token_against_db(
                session, state.token_signer, body.token, expected_action="revise",
            )
            request_id = UUID(claims["request_id"])
            actor_id = f"token:{claims.get('sub', 'mail')}"
            correlation_id = getattr(request.state, "correlation_id", None)
            result = await admin_service.admin_revise(
                session,
                request_id=request_id,
                request_version=body.request_version,
                team_id=body.team_id,
                max_parallel_requests=body.max_parallel_requests,
                admin_note=body.admin_note,
                models=body.models,
                response_window=body.response_window,
                usage_frequency=body.usage_frequency,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            await consume_winning_token(session, token_row)
            await session.commit()
    except (InvalidActionTokenError, KeyError, ValueError) as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get("INVALID_ACTION_TOKEN", 401),
            content={"error_code": "INVALID_ACTION_TOKEN", "detail": str(exc)},
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(
        content={"request_id": str(request_id), "status": result.new_status,
                 "snapshot_taken": result.snapshot_taken},
    )


@router.post("/reject", response_model=None)
async def post_reject(request: FastAPIRequest) -> JSONResponse:
    """Tüm automated tiplerde kullanılabilir; reject_reason bounded 1..2000."""
    body = PostRejectBody.model_validate(await request.json())

    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            claims, token_row = await verify_token_against_db(
                session, state.token_signer, body.token, expected_action="reject",
            )
            request_id = UUID(claims["request_id"])
            actor_id = f"token:{claims.get('sub', 'mail')}"
            correlation_id = getattr(request.state, "correlation_id", None)
            result = await admin_service.admin_reject(
                session,
                request_id=request_id,
                request_version=body.request_version,
                reject_reason=body.reject_reason,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            await consume_winning_token(session, token_row)
            await session.commit()
    except (InvalidActionTokenError, KeyError, ValueError) as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get("INVALID_ACTION_TOKEN", 401),
            content={"error_code": "INVALID_ACTION_TOKEN", "detail": str(exc)},
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(
        content={"request_id": str(request_id), "status": result.new_status},
    )

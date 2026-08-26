"""Admin panel: list/approve/revise/reject pending requests.

Talepler (list/detail/approve/revise/reject): giriş yapmış aktif kullanıcı.
Kullanıcı / onaylayan CRUD: ``is_superuser``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.src.api.auth.dependencies import get_current_user
from backend.src.api.utils import admin_service
from backend.src.data.db.models import User
from backend.src.data.db.models.requests import Request as RequestRow
from backend.src.domain.enums import VALID_ACTIONS_BY_TYPE, RequestType
from backend.src.domain.errors import DomainError

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_DOMAIN_ERROR_STATUS = {
    "INVALID_ACTION_TOKEN": 401,
    "ACTION_NOT_ALLOWED_FOR_TYPE": 409,
    "NOT_FOUND": 404,
    "ALREADY_PROCESSED": 200,
    "OPTIMISTIC_LOCK_CONFLICT": 409,
}


def _actor_id(user: User) -> str:
    return f"user:{user.username}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _row_to_detail_dict(row: RequestRow) -> dict:
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
    return {k: _json_safe(getattr(row, k)) for k in keys if getattr(row, k) is not None}


@router.get("/requests")
async def list_requests(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    status: str = "",
) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        stmt = select(RequestRow).order_by(RequestRow.created_at.desc()).limit(200)
        if status and status != "all":
            stmt = stmt.where(RequestRow.status == status)
        rows = (await session.execute(stmt)).scalars().all()
    return JSONResponse(
        content=[
            {
                "request_id": str(row.id),
                "request_type": row.request_type,
                "status": row.status,
                "genai_orion_panel_ticket_id": row.genai_orion_panel_ticket_id,
                "requester_name": row.requester_name,
                "requester_email": row.requester_email,
                "environment": row.environment,
                "created_at": row.created_at.isoformat(),
                "detail": _row_to_detail_dict(row),
            }
            for row in rows
        ]
    )


@router.get("/requests/{request_id}")
async def get_request_detail(
    request: Request,
    request_id: UUID,
    _user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        req = await session.get(RequestRow, request_id)
    if req is None:
        return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})

    detail = _row_to_detail_dict(req)
    try:
        rtype = RequestType(req.request_type)
    except ValueError:
        rtype = None
    available_actions = sorted(
        a.value for a in VALID_ACTIONS_BY_TYPE.get(rtype, frozenset())
    )
    created_at = req.genai_orion_panel_created_at or req.created_at
    return JSONResponse(
        content={
            "request_id": str(req.id),
            "request_type": req.request_type,
            "status": req.status,
            "request_version": req.version,
            "genai_orion_panel_ticket_id": req.genai_orion_panel_ticket_id,
            "genai_orion_panel_ticket_url": req.genai_orion_panel_ticket_url,
            "requester_name": req.requester_name,
            "requester_email": req.requester_email,
            "environment": req.environment or "",
            "created_at": created_at.isoformat() if created_at else None,
            "detail": detail,
            "available_actions": available_actions,
        }
    )


class AdminApproveBody(BaseModel):
    request_version: int = Field(ge=0)
    allows_all_tools: bool | None = None


class AdminReviseBody(BaseModel):
    request_version: int = Field(ge=0)
    team_id: Annotated[str, Field(min_length=1, max_length=128)]
    max_parallel_requests: int = Field(ge=1)
    admin_note: Annotated[str | None, Field(default=None, max_length=2000)] = None
    models: Annotated[list[str] | None, Field(default=None)] = None
    response_window: Annotated[str | None, Field(default=None, max_length=64)] = None
    usage_frequency: Annotated[str | None, Field(default=None, max_length=64)] = None
    snapshot_taken: Annotated[bool, Field(default=False)] = False


class AdminRejectBody(BaseModel):
    request_version: int = Field(ge=0)
    reject_reason: str = Field(min_length=1, max_length=2000)


@router.post("/requests/{request_id}/approve")
async def approve(
    request: Request,
    request_id: UUID,
    body: AdminApproveBody,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            result = await admin_service.admin_approve(
                session,
                request_id=request_id,
                request_version=body.request_version,
                allows_all_tools=body.allows_all_tools,
                actor_id=_actor_id(user),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
            await session.commit()
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": result.new_status})


@router.post("/requests/{request_id}/revise")
async def revise(
    request: Request,
    request_id: UUID,
    body: AdminReviseBody,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
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
                actor_id=_actor_id(user),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
            await session.commit()
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(
        content={
            "request_id": str(request_id),
            "status": result.new_status,
            "snapshot_taken": result.snapshot_taken,
        }
    )


@router.post("/requests/{request_id}/reject")
async def reject(
    request: Request,
    request_id: UUID,
    body: AdminRejectBody,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            result = await admin_service.admin_reject(
                session,
                request_id=request_id,
                request_version=body.request_version,
                reject_reason=body.reject_reason,
                actor_id=_actor_id(user),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
            await session.commit()
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": result.new_status})

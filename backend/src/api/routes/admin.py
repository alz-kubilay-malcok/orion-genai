"""Admin panel: bekleyen talepleri listeleme/işleme.

Bu modül artık oturum açma gerektirmez. Login ve kullanıcı yönetimi
kaldırıldı; LDAP entegrasyonu sonradan eklenecek. `actor_id` şimdilik
literal `anonymous` olarak geçilmektedir — actor alanı ham business
log'u için tutuluyor, kimlik doğrulama değil.

NOT: User CRUD endpoint'leri (`/admin/users/*` ve `/auth/*`) kaldırıldı.
Onlar kimlik doğrulama ve operatör yönetimi altındaydı; giriş akışı
LDAP'a taşınınca bu uç noktalar baz alınarak yeniden yapılandırılacak.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.src.adapters.postgres.models import RequestRow
from backend.src.domain.enums import (
    VALID_ACTIONS_BY_TYPE,
)
from backend.src.domain.errors import DomainError

from backend.src.api.auth.dependencies import try_get_current_user
from backend.src.api.utils import admin_service
from backend.src.data.db.models import User

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# LDAP geçişiyle birlikte: Bearer gelirse gerçek user.username; gelmezse
# legacy "anonymous" fallback (kaldırılmadı; ileride zorunlu auth'a çekilecek).
_UNAUTHENTICATED_ACTOR = "anonymous"
_OPTIONAL_BEARER = HTTPBearer(auto_error=False)


def _resolve_actor_id(user: User | None) -> str:
    """``try_get_current_user`` dönüşünden audit'e yazılacak kimliği çöz."""
    if user is None:
        return _UNAUTHENTICATED_ACTOR
    return f"user:{user.username}"


def _row_to_detail_dict(row: RequestRow) -> dict:
    """ORM satırından detail dict'i çıkar (legacy ``req.detail`` taklidi).

    Bu refactor turunda ``backend.src.domain.entities.request.Request``
    yazılmadığı için, client-facing alanlar doğrudan ORM kolonlarından
    toplanır. ``asdict(req.detail)`` çağrısının yerine şeffaf bir
    ``dict(filter(lambda kv: kv[1] is not None, ...))`` filtresi yeterli.
    Kolon adları kwargs sözlüğünden legacy alan isimleriyle eşleşir
    (frontend ``actionSchema.ts``/``adminApi.ts`` ile hizalı).
    """
    # LitellmKey detail alanları
    keys = (
        "department_name", "request_description", "purpose_code",
        "use_case", "models", "response_window", "usage_frequency",
        "estimated_daily_requests", "max_concurrent_requests",
        "input_pages", "output_pages", "estimated_tokens_per_request",
        "estimated_peak_rpm", "estimated_peak_tpm",
        "tpm_approved", "rpm_approved", "key_alias",
        # MCPKey detail alanları
        "mcp_server_slug", "mcp_tool_names", "all_tools",
        "registry_allows_all_tools",
        # MCPRegistry detail alanları
        "mcp_server_display_name", "project_name", "technical_owner_email",
        "repo_platform", "repo_url", "devops_jira_key",
        "mcp_endpoint_url", "minimum_evaluation_score",
    )
    return {k: getattr(row, k) for k in keys if getattr(row, k) is not None}


@router.get("/requests")
async def list_requests(request: Request, status: str = "") -> JSONResponse:
    """Talepleri listele.

    `status` query parametresi opsiyoneldir:
    - boş / "all" → tüm statüler (client-side `requestStatus.ts` filtre dropdown'ı bunları
      kendi içinde ayırır). Önceden varsayılan `waiting_approval` idi; bu, yeni alınan bir
      talep webhook tarafından hâlâ `received`/`provisioning` vb. olabilen başka
      statülere geçtiğinde admin panelinden tamamen kaybolmasına yol açıyordu.
    - aksi halde tam eşleşme (örn. "completed", "rejected").
    """
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
async def get_request_detail(request: Request, request_id: UUID) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.new_uow() as uow:
        req = await uow.requests.get_by_id(request_id)
        await uow.rollback()

    if req is None:
        return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})

    detail = _row_to_detail_dict(req)
    # Available actions: type icin izinli eylemlerden type.value string'leri.
    from backend.src.domain.enums import RequestType
    try:
        rtype = RequestType(req.request_type)
    except ValueError:
        rtype = None
    available_actions = sorted(
        a.value for a in VALID_ACTIONS_BY_TYPE.get(rtype, frozenset())
    )
    return JSONResponse(
        content={
            "request_id": str(req.id),
            "request_type": req.request_type,                                # str (ORM)
            "status": req.status,                                            # str (ORM)
            "request_version": req.version,
            "genai_orion_panel_ticket_id": req.genai_orion_panel_ticket_id,
            "genai_orion_panel_ticket_url": req.genai_orion_panel_ticket_url,
            "requester_name": req.requester_name,
            "requester_email": req.requester_email,
            "environment": req.environment or "",                            # ORM Optional[str]
            "created_at": req.genai_orion_panel_created_at.isoformat(),
            "detail": detail,
            "available_actions": available_actions,
        }
    )


class AdminApproveBody(BaseModel):
    request_version: int = Field(ge=0)
    allows_all_tools: bool | None = None


class AdminReviseBody(BaseModel):
    """Admin panel `POST /admin/requests/{id}/revise` gövdesi.

    Operasyonel alanlar zorunludur (``tpm_approved`` / ``rpm_approved``).
    Client-facing üç alan (``models`` / ``response_window`` / ``usage_frequency``)
    opsiyoneldir: ``None`` = alana dokunulmaz; boş liste/str = bilinçli sıfırlama.
    """

    request_version: int = Field(ge=0)
    tpm_approved: int = Field(gt=0)
    rpm_approved: int = Field(gt=0)
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
    user: Annotated[User | None, Depends(try_get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            result = await admin_service.admin_approve(
                session,
                request_id=request_id,
                request_version=body.request_version,
                allows_all_tools=body.allows_all_tools,
                actor_id=_resolve_actor_id(user),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
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
    user: Annotated[User | None, Depends(try_get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            result = await admin_service.admin_revise(
                session,
                request_id=request_id,
                request_version=body.request_version,
                tpm_approved=body.tpm_approved,
                rpm_approved=body.rpm_approved,
                admin_note=body.admin_note,
                models=body.models,
                response_window=body.response_window,
                usage_frequency=body.usage_frequency,
                actor_id=_resolve_actor_id(user),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": result.new_status, "snapshot_taken": result.snapshot_taken})


@router.post("/requests/{request_id}/reject")
async def reject(
    request: Request,
    request_id: UUID,
    body: AdminRejectBody,
    user: Annotated[User | None, Depends(try_get_current_user)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        async with state.session_factory() as session:
            result = await admin_service.admin_reject(
                session,
                request_id=request_id,
                request_version=body.request_version,
                reject_reason=body.reject_reason,
                actor_id=_resolve_actor_id(user),
                correlation_id=getattr(request.state, "correlation_id", None),
            )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": result.new_status})


# Bu modülde eskiden /admin/users* CRUD uç noktaları vardı. Şifre temelli
# local auth kaldırıldığı için geçici olarak devre dışı. LDAP hazır olunca
# aynı sözleşmeyle (kullanıcı listeleme, şifre sıfırlama olmadan) geri
# gelecek. Frontend `AdminRequestActions.tsx` ve admin/users sayfası bu
# endpoint'leri bekliyorsa ayrıca güncellenmeli.

_DOMAIN_ERROR_STATUS = {
    "INVALID_ACTION_TOKEN": 401,
    "ACTION_NOT_ALLOWED_FOR_TYPE": 409,
    "NOT_FOUND": 404,
    "ALREADY_PROCESSED": 200,
    "OPTIMISTIC_LOCK_CONFLICT": 409,
}

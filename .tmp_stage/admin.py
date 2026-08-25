"""Admin panel: bekleyen talepleri listeleme/işleme + kullanıcı yönetimi.

Pilot ekleme, baseline dışı. Session-cookie authenticated; approval token
gerektirmez (bkz. `admin_service.py`).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from genai_orion_panel_adapters.postgres import users as users_repo
from genai_orion_panel_adapters.postgres.models import MailMessageRow, RequestRow, UserRow
from genai_orion_panel_core.domain.enums import VALID_ACTIONS_BY_TYPE, RequestType
from genai_orion_panel_core.domain.errors import DomainError

from genai_orion_panel_api import admin_service
from genai_orion_panel_api.security.passwords import hash_password
from genai_orion_panel_api.security.session import SESSION_COOKIE_NAME, verify_session_cookie

if TYPE_CHECKING:
    from genai_orion_panel_api.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_DOMAIN_ERROR_STATUS = {
    "NOT_FOUND": 404,
    "ACTION_NOT_ALLOWED_FOR_TYPE": 409,
    "OPTIMISTIC_LOCK_CONFLICT": 409,
    "LITELLM_ESTIMATE_MISSING": 409,
}


class CurrentOperator(BaseModel):
    user_id: str
    username: str
    is_admin: bool


class CurrentAdmin(BaseModel):
    user_id: str
    username: str
    is_admin: bool = True


def _resolve_session(request: Request) -> dict[str, object]:
    state: AppState = request.app.state.container
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        raise HTTPException(status_code=401, detail="Oturum yok")
    try:
        return verify_session_cookie(state.token_signer, cookie_value)
    except DomainError as exc:
        raise HTTPException(status_code=401, detail="Oturum geçersiz") from exc


async def require_operator(request: Request) -> CurrentOperator:
    """Authenticated herhangi bir kullanıcı (admin veya operator).

    Talep listeleme + approve/revise/reject tüm yetkili kullanıcılara açıktır.
    Sadece user yönetimi admin ayrıcalığıdır.
    """
    claims = _resolve_session(request)
    is_admin = bool(claims.get("is_admin"))
    return CurrentOperator(
        user_id=str(claims["user_id"]),
        username=str(claims["username"]),
        is_admin=is_admin,
    )


async def require_admin(request: Request) -> CurrentAdmin:
    """Sadece admin yetkisi gerektiren işlemler (kullanıcı yönetimi)."""
    claims = _resolve_session(request)
    if not claims.get("is_admin"):
        raise HTTPException(status_code=403, detail="Bu işlem yalnızca admin içindir")
    return CurrentAdmin(
        user_id=str(claims["user_id"]), username=str(claims["username"]), is_admin=True
    )


OperatorDep = Annotated[CurrentOperator, Depends(require_operator)]
AdminDep = Annotated[CurrentAdmin, Depends(require_admin)]


# ---- Requests ---------------------------------------------------------


@router.get("/requests")
async def list_requests(request: Request, op: OperatorDep, status: str = "") -> JSONResponse:
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
            }
            for row in rows
        ]
    )


@router.get("/requests/{request_id}")
async def get_request_detail(request: Request, op: OperatorDep, request_id: UUID) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.new_uow() as uow:
        req = await uow.requests.get_by_id(request_id)
        await uow.rollback()

    if req is None:
        return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})

    detail = asdict(req.detail) if req.detail is not None else {}
    available_actions = sorted(a.value for a in VALID_ACTIONS_BY_TYPE.get(req.request_type, frozenset()))
    return JSONResponse(
        content={
            "request_id": str(req.id),
            "request_type": req.request_type.value,
            "status": req.status.value,
            "request_version": req.version,
            "genai_orion_panel_ticket_id": req.genai_orion_panel_ticket_id,
            "genai_orion_panel_ticket_url": req.genai_orion_panel_ticket_url,
            "requester_name": req.requester_name,
            "requester_email": req.requester_email,
            "environment": req.environment.value if req.environment is not None else "",
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
async def approve(request: Request, op: OperatorDep, request_id: UUID, body: AdminApproveBody) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        _, new_status = await admin_service.admin_approve(
            state.new_uow(),
            request_id=request_id,
            request_version=body.request_version,
            allows_all_tools=body.allows_all_tools,
            actor_id=op.username,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": new_status.value})


@router.post("/requests/{request_id}/revise")
async def revise(request: Request, op: OperatorDep, request_id: UUID, body: AdminReviseBody) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        _, new_status, _snapshot = await admin_service.admin_revise(
            state.new_uow(),
            request_id=request_id,
            request_version=body.request_version,
            tpm_approved=body.tpm_approved,
            rpm_approved=body.rpm_approved,
            admin_note=body.admin_note,
            models=body.models,
            response_window=body.response_window,
            usage_frequency=body.usage_frequency,
            actor_id=op.username,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": new_status.value})


@router.post("/requests/{request_id}/reject")
async def reject(request: Request, op: OperatorDep, request_id: UUID, body: AdminRejectBody) -> JSONResponse:
    state: AppState = request.app.state.container
    try:
        _, new_status = await admin_service.admin_reject(
            state.new_uow(),
            request_id=request_id,
            request_version=body.request_version,
            reject_reason=body.reject_reason,
            actor_id=op.username,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=_DOMAIN_ERROR_STATUS.get(exc.error_code, 422),
            content={"error_code": exc.error_code},
        )
    return JSONResponse(content={"request_id": str(request_id), "status": new_status.value})


# ---- Users --------------------------------------------------------------


class CreateUserBody(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    email: str = Field(min_length=3, max_length=255)
    # Sistem tek admin; admin her zaman ADMIN_USERNAME/ADMIN_PASSWORD env'den seed edilir.
    # API üzerinden admin hesabı açılamaz; is_admin alanı yok sayılır.
    model_config = {"extra": "ignore"}


class PatchUserBody(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    is_active: bool | None = None
    model_config = {"extra": "ignore"}


@router.get("/users")
async def list_users(request: Request, admin: AdminDep) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        records = await users_repo.list_users(session)
    return JSONResponse(
        content=[
            {
                "id": str(r.id),
                "username": r.username,
                "email": r.email,
                "is_admin": r.is_admin,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
    )


@router.post("/users")
async def create_user(request: Request, admin: AdminDep, body: CreateUserBody) -> JSONResponse:
    state: AppState = request.app.state.container
    email_value = body.email.strip().lower()
    if "@" not in email_value or len(email_value) > 255:
        raise HTTPException(status_code=422, detail="Geçerli bir e-posta adresi girin")
    async with state.session_factory() as session:
        existing = await users_repo.get_by_username(session, body.username.strip())
        if existing is not None:
            raise HTTPException(status_code=409, detail="Kullanıcı adı zaten kullanımda")
        existing_email = await users_repo.get_by_email(session, email_value)
        if existing_email is not None:
            raise HTTPException(status_code=409, detail="E-posta zaten kullanımda")
        record = await users_repo.create_user(
            session,
            username=body.username.strip(),
            password_hash=hash_password(body.password),
            email=email_value,
            is_admin=False,  # Sistem tek admin; açılan her hesap operatördür.
            is_active=True,
        )
    return JSONResponse(
        content={
            "id": str(record.id),
            "username": record.username,
            "email": record.email,
            "is_admin": record.is_admin,
            "is_active": record.is_active,
            "created_at": record.created_at.isoformat(),
        }
    )


@router.patch("/users/{user_id}")
async def patch_user(
    request: Request,
    admin: AdminDep,
    user_id: UUID,
    body: "PatchUserBody",
) -> JSONResponse:
    """Sadece `email` ve `is_active` alanları güncellenebilir.

    Username/password update'ler pilot kapsamdışı; admin ayrıcalığı password
    reset eklemek ticket'a düşünülebilir.
    """
    state: AppState = request.app.state.container

    async def _refresh(target_id: UUID) -> Any:
        async with state.session_factory() as session:
            return await users_repo.get_by_id(session, target_id)

    async with state.session_factory() as session:
        target = await users_repo.get_by_id(session, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        if target.is_admin and body.is_active is False:
            # Admin pasifleştirilemez (env seed'ini kaybederiz).
            raise HTTPException(status_code=409, detail="Admin hesabı pasif yapılamaz")

        if body.email is not None:
            new_email = body.email.strip().lower()
            if "@" not in new_email or len(new_email) > 255:
                raise HTTPException(
                    status_code=422, detail="Geçerli bir e-posta adresi girin"
                )
            other = await users_repo.get_by_email(session, new_email)
            if other is not None and other.id != user_id:
                raise HTTPException(status_code=409, detail="E-posta zaten kullanımda")
            await users_repo.update_email(session, user_id=user_id, email=new_email)

        if body.is_active is not None:
            await users_repo.update_is_active(
                session, user_id=user_id, is_active=body.is_active
            )

    record = await _refresh(user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return JSONResponse(
        content={
            "id": str(record.id),
            "username": record.username,
            "email": record.email,
            "is_admin": record.is_admin,
            "is_active": record.is_active,
            "created_at": record.created_at.isoformat(),
        }
    )


@router.delete("/users/{user_id}")
async def delete_user(request: Request, admin: AdminDep, user_id: UUID) -> JSONResponse:
    if str(user_id) == admin.user_id:
        raise HTTPException(status_code=400, detail="Kendi hesabınızı silemezsiniz")
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        target = await users_repo.get_by_id(session, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        if target.is_admin:
            # Admin tekildir ve env'den yönetilir; API üzerinden silinemez.
            raise HTTPException(status_code=409, detail="Admin hesabı silinemez")
        deleted = await users_repo.delete_user(session, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return JSONResponse(content={"ok": True})


# ---- Mail messages (DB-backed mailbox) -----------------------------------
#
# `MAIL_PROVIDER=db` adapter'i tarafindan yazilan mailler. Streamlit Orion
# Studio bu endpoint'i dosya sistemi yerine kullanir. Listeleme hem UI hem
# admin panel icin ortaktir; filtreler opsiyoneldir.

_MAIL_LIMIT_DEFAULT = 200


class MailMessageResponse(BaseModel):
    model_config = {"extra": "ignore"}

    id: str
    template: str
    subject: str
    from_email: str
    recipients: list[str]
    context: dict[str, object]
    body_text: str | None = None
    body_html: str | None = None
    has_secret: bool
    correlation_id: str | None = None
    app_env: str
    delivery_status: str
    request_id: str | None = None
    read_at: str | None = None
    read_by_user_id: str | None = None
    created_at: str


def _serialize_mail(row: MailMessageRow) -> dict[str, object]:
    return {
        "id": str(row.id),
        "template": row.template,
        "subject": row.subject,
        "from_email": row.from_email,
        "recipients": list(row.recipients or []),
        "context": dict(row.context or {}),
        "body_text": row.body_text,
        "body_html": row.body_html,
        "has_secret": bool(row.has_secret),
        "correlation_id": row.correlation_id,
        "app_env": row.app_env,
        "delivery_status": row.delivery_status,
        "request_id": str(row.request_id) if row.request_id else None,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "read_by_user_id": str(row.read_by_user_id) if row.read_by_user_id else None,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/mail/messages")
async def list_mail_messages(
    request: Request,
    op: OperatorDep,
    unread_only: bool = False,
    template: str | None = None,
    request_id: UUID | None = None,
    limit: int = _MAIL_LIMIT_DEFAULT,
) -> JSONResponse:
    """Mailbox listesi.

    - `unread_only=true`: yalnizca `read_at IS NULL` olan mailler.
    - `template`: tam esleme (orn. `result_rejected`).
    - `request_id`: tek bir talebe ait mailler.
    - `limit`: varsayilan 200; min 1, max 1000.
    """
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit 1..1000")
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        stmt = select(MailMessageRow).order_by(MailMessageRow.created_at.desc()).limit(limit)
        if unread_only:
            stmt = stmt.where(MailMessageRow.read_at.is_(None))
        if template:
            stmt = stmt.where(MailMessageRow.template == template)
        if request_id:
            stmt = stmt.where(MailMessageRow.request_id == request_id)
        rows = (await session.execute(stmt)).scalars().all()
    return JSONResponse(content=[_serialize_mail(r) for r in rows])


@router.post("/mail/messages/{message_id}/read")
async def mark_mail_read(
    request: Request,
    op: OperatorDep,
    message_id: UUID,
) -> JSONResponse:
    """Bir maili "okundu" olarak isaretle.

    Birden fazla admin/operator ayni maili goruntulediginde son read bilgisi
    DB'ye yazilir. Tekrar tekrar okunabilir — `read_at=en son islem` kalir.
    """
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        row = await session.get(MailMessageRow, message_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Mail bulunamadı")
        if row.read_at is None:
            row.read_at = datetime.now(UTC)
            # read_by_user_id UserRow FK; user_id string ise sadece update edebilmek
            # icin UUID'ye donusturulur (None/parse-fail durumunda atlanir).
            try:
                row.read_by_user_id = UUID(op.user_id)
            except ValueError:
                row.read_by_user_id = None
            await session.commit()
            await session.refresh(row)
    return JSONResponse(content=_serialize_mail(row))


@router.post("/mail/messages/mark-all-read")
async def mark_all_mail_read(request: Request, op: OperatorDep) -> JSONResponse:
    """Tum okunmamis mailleri okundu olarak isaretle."""
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        stmt = select(MailMessageRow).where(MailMessageRow.read_at.is_(None))
        rows = (await session.execute(stmt)).scalars().all()
        now = datetime.now(UTC)
        try:
            user_uuid = UUID(op.user_id)
        except ValueError:
            user_uuid = None
        for row in rows:
            row.read_at = now
            row.read_by_user_id = user_uuid
        await session.commit()
    return JSONResponse(content={"updated": len(rows)})

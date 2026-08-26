"""Admin directory: approvers + users (is_superuser)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.src.api.auth.dependencies import get_current_superuser
from backend.src.data.db.models import User
from backend.src.data.db.models.config_approvers import ConfigApprover

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

router = APIRouter(prefix="/admin", tags=["admin"])


_APPROVER_SCOPE = "GENAI_APPROVAL"


def _approver_json(row: ConfigApprover) -> dict[str, Any]:
    created = row.created_at
    return {
        "id": str(row.id),
        "email": row.email,
        "scope": row.scope,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
        "created_at": created.isoformat() if created is not None else None,
    }


class ApproverCreateBody(BaseModel):
    email: EmailStr


class ApproverPatchBody(BaseModel):
    is_active: bool | None = None
    sort_order: Annotated[int | None, Field(default=None, ge=0)] = None


@router.get("/approvers")
async def list_approvers(
    request: Request,
    _user: Annotated[User, Depends(get_current_superuser)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        rows = (
            await session.execute(
                select(ConfigApprover)
                .where(ConfigApprover.scope == _APPROVER_SCOPE)
                .order_by(ConfigApprover.sort_order.asc(), ConfigApprover.email.asc())
            )
        ).scalars().all()
    return JSONResponse(content=[_approver_json(row) for row in rows])


@router.post("/approvers")
async def create_approver(
    request: Request,
    body: ApproverCreateBody,
    _user: Annotated[User, Depends(get_current_superuser)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    email = str(body.email).strip().lower()
    async with state.session_factory() as session:
        existing = (
            await session.execute(
                select(ConfigApprover).where(
                    ConfigApprover.email == email,
                    ConfigApprover.scope == _APPROVER_SCOPE,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.is_active:
                return JSONResponse(
                    status_code=409,
                    content={"error_code": "ALREADY_EXISTS", "id": str(existing.id)},
                )
            existing.is_active = True
            await session.commit()
            await session.refresh(existing)
            return JSONResponse(status_code=200, content=_approver_json(existing))
        max_order = (
            await session.execute(
                select(ConfigApprover.sort_order)
                .where(ConfigApprover.scope == _APPROVER_SCOPE)
                .order_by(ConfigApprover.sort_order.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        row = ConfigApprover(
            id=uuid4(),
            email=email,
            scope=_APPROVER_SCOPE,
            sort_order=(max_order or 0) + 1,
            is_active=True,
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return JSONResponse(
                status_code=409,
                content={"error_code": "ALREADY_EXISTS"},
            )
        await session.refresh(row)
        return JSONResponse(status_code=201, content=_approver_json(row))


@router.patch("/approvers/{approver_id}")
async def patch_approver(
    request: Request,
    approver_id: UUID,
    body: ApproverPatchBody,
    _user: Annotated[User, Depends(get_current_superuser)],
) -> JSONResponse:
    if body.is_active is None and body.sort_order is None:
        return JSONResponse(status_code=422, content={"error_code": "EMPTY_PATCH"})
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        row = await session.get(ConfigApprover, approver_id)
        if row is None or row.scope != _APPROVER_SCOPE:
            return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})
        if body.is_active is not None:
            row.is_active = body.is_active
        if body.sort_order is not None:
            row.sort_order = body.sort_order
        await session.commit()
        await session.refresh(row)
        return JSONResponse(content=_approver_json(row))


@router.delete("/approvers/{approver_id}")
async def delete_approver(
    request: Request,
    approver_id: UUID,
    _user: Annotated[User, Depends(get_current_superuser)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        row = await session.get(ConfigApprover, approver_id)
        if row is None or row.scope != _APPROVER_SCOPE:
            return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})
        await session.delete(row)
        await session.commit()
    return Response(status_code=204)


# ---- Users (LDAP admin group + bootstrap admin = is_superuser) -----------

def _user_json(row: User, *, is_approver: bool = False) -> dict[str, Any]:
    last = row.last_login_at
    created = row.created_at
    return {
        "id": str(row.id),
        "username": row.username,
        "email": row.email,
        "display_name": row.display_name,
        "is_superuser": row.is_superuser,
        "is_active": row.is_active,
        "is_approver": is_approver,
        "is_ldap": bool(row.ldap_dn),
        "last_login_at": last.isoformat() if last is not None else None,
        "created_at": created.isoformat() if created is not None else None,
    }


async def _approver_email_set(session: object) -> set[str]:
    rows = (
        await session.execute(  # type: ignore[union-attr]
            select(ConfigApprover.email).where(
                ConfigApprover.scope == _APPROVER_SCOPE,
                ConfigApprover.is_active.is_(True),
            )
        )
    ).scalars().all()
    return {str(email).strip().lower() for email in rows}


async def _set_user_approver(session: object, email: str, *, enabled: bool) -> None:
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise ValueError("NO_EMAIL")
    existing = (
        await session.execute(  # type: ignore[union-attr]
            select(ConfigApprover).where(
                ConfigApprover.email == normalized,
                ConfigApprover.scope == _APPROVER_SCOPE,
            )
        )
    ).scalar_one_or_none()
    if enabled:
        if existing is None:
            session.add(ConfigApprover(  # type: ignore[union-attr]
                id=uuid4(),
                email=normalized,
                scope=_APPROVER_SCOPE,
                sort_order=0,
                is_active=True,
            ))
        else:
            existing.is_active = True
        return
    if existing is not None:
        existing.is_active = False


def _bootstrap_username(request: Request) -> str:
    state: AppState = request.app.state.container
    return (state.settings.bootstrap_admin_username or "").strip()


class UserPatchBody(BaseModel):
    is_superuser: bool | None = None
    is_active: bool | None = None
    is_approver: bool | None = None


@router.get("/users")
async def list_users(
    request: Request,
    _user: Annotated[User, Depends(get_current_superuser)],
) -> JSONResponse:
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        rows = (
            await session.execute(
                select(User).order_by(User.is_superuser.desc(), User.username.asc())
            )
        ).scalars().all()
        approvers = await _approver_email_set(session)
    return JSONResponse(
        content=[
            _user_json(row, is_approver=(row.email or "").strip().lower() in approvers)
            for row in rows
        ]
    )


@router.patch("/users/{user_id}")
async def patch_user(
    request: Request,
    user_id: UUID,
    body: UserPatchBody,
    actor: Annotated[User, Depends(get_current_superuser)],
) -> JSONResponse:
    if body.is_superuser is None and body.is_active is None and body.is_approver is None:
        return JSONResponse(status_code=422, content={"error_code": "EMPTY_PATCH"})
    bootstrap = _bootstrap_username(request)
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        row = await session.get(User, user_id)
        if row is None:
            return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND"})
        if row.username == bootstrap or row.id == actor.id:
            demote = body.is_superuser is False or body.is_active is False
            if demote:
                return JSONResponse(
                    status_code=409,
                    content={"error_code": "PROTECTED_ACCOUNT"},
                )
        if body.is_superuser is not None:
            row.is_superuser = body.is_superuser
        if body.is_active is not None:
            row.is_active = body.is_active
        if body.is_approver is not None:
            try:
                await _set_user_approver(session, row.email or "", enabled=body.is_approver)
            except ValueError:
                return JSONResponse(
                    status_code=422,
                    content={"error_code": "NO_EMAIL"},
                )
        await session.commit()
        await session.refresh(row)
        approvers = await _approver_email_set(session)
        return JSONResponse(
            content=_user_json(
                row,
                is_approver=(row.email or "").strip().lower() in approvers,
            )
        )


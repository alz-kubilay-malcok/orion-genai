"""``/admin/ldap-mappings/*`` — kılavuz §5 LDAP group→role mapping yönetimi.

Üç endpoint, üçü de org-level ADMIN yetkisi gerektirir:

- GET    /admin/ldap-mappings?org_id=<uuid>                    → list
- POST   /admin/ldap-mappings   {org_id, group_dn, role, ns?}  → 201 | 404 | 409
- DELETE /admin/ldap-mappings/{id}                              → 204

Tüm mutasyonlar ``audit_log`` tablosuna satır yazar (append-only).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.auth.dependencies import (
    get_current_user,
    get_db_session,
)
from backend.src.api.auth.schemas import (
    LdapMappingCreate,
    LdapMappingItem,
)
from backend.src.data.db.models import (
    AuditLog,
    LdapGroupMapping,
    Namespace,
    Organization,
    Role,
    RoleBinding,
    RoleBindingSource,
    User,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/ldap-mappings", tags=["admin-ldap"])


# ---- helpers -------------------------------------------------------------

async def _require_org_admin(
    session: AsyncSession, user: User, org_id: UUID,
) -> None:
    """Yetki kontrolü.

    Süper user (bootstrap admin) her org'a admin. Aksi halde kullanıcının
    ``roles`` tablosunda adı ``admin`` olan bir binding'i (org-wide veya
    ilgili namespace'te) olmalı.
    """
    if user.is_superuser:
        return
    admin_role = (await session.execute(
        select(Role).where(Role.name == "admin")
    )).scalar_one_or_none()
    if admin_role is None:
        raise HTTPException(status_code=503, detail="admin role missing — seed çalıştırılmamış")
    binding = (await session.execute(
        select(RoleBinding.id).where(
            RoleBinding.user_id == user.id,
            RoleBinding.role_id == admin_role.id,
            RoleBinding.org_id == org_id,
        ).limit(1)
    )).scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=403, detail="admin permission required for this org")


async def _resolve_role(session: AsyncSession, role_name: str) -> Role:
    role = (await session.execute(
        select(Role).where(Role.name == role_name)
    )).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail=f"role not found: {role_name!r}")
    return role


async def _resolve_org(session: AsyncSession, org_id: UUID) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail=f"org not found: {org_id}")
    return org


async def _resolve_namespace(
    session: AsyncSession, org_id: UUID, namespace_id: UUID | None,
) -> Namespace | None:
    if namespace_id is None:
        return None
    ns = await session.get(Namespace, namespace_id)
    if ns is None or ns.org_id != org_id:
        raise HTTPException(
            status_code=404,
            detail=f"namespace not found in org: {namespace_id}",
        )
    return ns


async def _write_audit(
    session: AsyncSession,
    *,
    actor: User,
    action: str,
    target_id: str,
    target_type: str,
    payload: dict,
    correlation_id: str | None,
) -> None:
    session.add(AuditLog(
        id=uuid4(),
        actor_id=str(actor.id),
        actor_type="user",
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        correlation_id=correlation_id,
    ))
    await session.flush()


# ---- list ---------------------------------------------------------------

@router.get("", response_model=list[LdapMappingItem])
async def list_mappings(
    org_id: Annotated[UUID, Query(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[LdapMappingItem]:
    await _require_org_admin(session, user, org_id)
    rows = (await session.execute(
        select(LdapGroupMapping, Role.name).join(
            Role, Role.id == LdapGroupMapping.role_id,
        ).where(LdapGroupMapping.org_id == org_id)
        .order_by(LdapGroupMapping.created_at.desc())
    )).all()
    return [
        LdapMappingItem(
            id=str(m.id),
            org_id=str(m.org_id),
            group_dn=m.group_dn,
            role=role_name,
            role_id=str(m.role_id),
            namespace_id=str(m.namespace_id) if m.namespace_id else None,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m, role_name in rows
    ]


# ---- create -------------------------------------------------------------

@router.post("", response_model=LdapMappingItem, status_code=status.HTTP_201_CREATED)
async def create_mapping(
    body: LdapMappingCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LdapMappingItem:
    org_id = UUID(body.org_id)
    namespace_id = UUID(body.namespace_id) if body.namespace_id else None

    await _require_org_admin(session, user, org_id)
    await _resolve_org(session, org_id)
    role = await _resolve_role(session, body.role)
    await _resolve_namespace(session, org_id, namespace_id)

    mapping = LdapGroupMapping(
        id=uuid4(),
        group_dn=body.group_dn,
        role_id=role.id,
        org_id=org_id,
        namespace_id=namespace_id,
    )
    session.add(mapping)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="mapping already exists (group_dn, role, org, namespace)",
        ) from exc

    await _write_audit(
        session,
        actor=user,
        action="ldap_mapping.create",
        target_id=str(mapping.id),
        target_type="ldap_group_mapping",
        payload={
            "org_id": str(org_id),
            "group_dn": body.group_dn,
            "role": body.role,
            "namespace_id": str(namespace_id) if namespace_id else None,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    await session.commit()
    return LdapMappingItem(
        id=str(mapping.id),
        org_id=str(org_id),
        group_dn=body.group_dn,
        role=body.role,
        role_id=str(role.id),
        namespace_id=str(namespace_id) if namespace_id else None,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )


# ---- delete -------------------------------------------------------------

@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    mapping = await session.get(LdapGroupMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="mapping not found")

    # Once org admin on the mapping's org.
    await _require_org_admin(session, user, mapping.org_id)

    role_name = (await session.execute(
        select(Role.name).where(Role.id == mapping.role_id)
    )).scalar_one_or_none()
    await session.flush()

    # Delete LDAP-source bindings matching this (group_dn, role_id, org_id, ns)
    # Eğer kullanıcının artık başka mapping'i yoksa, bu satırı silmek
    # yetkisinin kesilmesi anlamına gelir. Manuel grants korunur.
    ldap_bindings = (await session.execute(
        select(RoleBinding).where(
            RoleBinding.role_id == mapping.role_id,
            RoleBinding.org_id == mapping.org_id,
            RoleBinding.namespace_id == mapping.namespace_id,
            RoleBinding.source == RoleBindingSource.LDAP,
        )
    )).scalars().all()
    revoked_count = 0
    for binding in ldap_bindings:
        # Bu kullanıcının hâlâ başka mapping'i var mı kontrol et — eğer
        # evet, binding'i tutmak "stale" olur; mapping silindiğine göre
        # revoke edilmeli.
        await session.delete(binding)
        revoked_count += 1

    await _write_audit(
        session,
        actor=user,
        action="ldap_mapping.delete",
        target_id=str(mapping_id),
        target_type="ldap_group_mapping",
        payload={
            "org_id": str(mapping.org_id),
            "group_dn": mapping.group_dn,
            "role": role_name,
            "namespace_id": str(mapping.namespace_id) if mapping.namespace_id else None,
            "ldap_bindings_revoked": revoked_count,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    await session.delete(mapping)
    await session.commit()
    return JSONResponse(status_code=204, content=None)


__all__ = ["router"]

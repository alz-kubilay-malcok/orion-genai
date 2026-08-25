"""Role + permission seed script.

Idempotent: var olan rolleri/izinleri atlar, eksik olanları ekler.
``--reset`` ile var olan management bindings dokunulmadan baştan kurulur
(role + permission tanım level'ında — kullanıcı/role_bindings değil).

İlk deploy'dan sonra çalıştırılması gerekir; LDAP entegrasyonu admin
mapping endpoint'leri (``/admin/ldap-mappings``) bu rollere referans verir.

Kullanım::

    cd backend && python -m scripts.seed_roles
    cd backend && python -m scripts.seed_roles --reset
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.src.api.utils.dependencies import build_app_state
from backend.src.data.db.models import Permission, Role, RolePermission

logger = logging.getLogger(__name__)


# Default rol + izin takımı — kılavuz §2 roster ile uyumlu.
DEFAULT_ROLES: dict[str, list[str]] = {
    "admin": [
        "*",  # wildcard: tüm `permission.code < action` çiftleri için geçerli
    ],
    "editor": [
        "request:approve",
        "request:reject",
        "request:revise",
        "request:list",
    ],
    "viewer": [
        "request:list",
        "request:read",
        "namespace:read",
    ],
    "redteam_operator": [
        "namespace:read",
        "request:list",
        "request:read",
    ],
}


async def _ensure_permission(session, code: str) -> Permission:
    existing = (await session.execute(
        select(Permission).where(Permission.code == code)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    perm = Permission(id=uuid4(), code=code)
    session.add(perm)
    await session.flush()
    return perm


async def _ensure_role(session, name: str) -> Role:
    existing = (await session.execute(
        select(Role).where(Role.name == name)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    role = Role(id=uuid4(), name=name)
    session.add(role)
    await session.flush()
    return role


async def _ensure_role_permission(session, role: Role, perm: Permission) -> bool:
    existing = (await session.execute(
        select(RolePermission).where(
            RolePermission.role_id == role.id,
            RolePermission.permission_id == perm.id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    return True


async def seed_roles(*, reset: bool = False) -> None:
    state = await build_app_state()
    try:
        async with state.session_factory() as session:
            if reset:
                # bindings + roles silinmez (kullanıcıların yetkisi gitmesin);
                # sadece ROLE↔PERMISSION bağlantıları sıfırlanır.
                await session.execute(text("DELETE FROM role_permissions"))
                logger.info("reset: role_permissions silindi")

            # 1) Tüm permission code'larını gather et
            codes: set[str] = set()
            for perms in DEFAULT_ROLES.values():
                codes.update(perms)

            # 2) Permission'ları ensure et
            code_to_perm = {}
            for code in sorted(codes):
                code_to_perm[code] = await _ensure_permission(session, code)

            # 3) Rol'ları ensure et ve binding'leri bağla
            created_roles: list[str] = []
            created_links: int = 0
            for role_name, perm_codes in DEFAULT_ROLES.items():
                role = await _ensure_role(session, role_name)
                # Yeni mi?
                if role.id and (await session.execute(
                    select(RolePermission).where(RolePermission.role_id == role.id).limit(1)
                )).first() is None:
                    created_roles.append(role_name)
                for code in perm_codes:
                    perm = code_to_perm[code]
                    if await _ensure_role_permission(session, role, perm):
                        created_links += 1

            await session.commit()
            logger.info(
                "seed ok: roles=%s yeni %d | r-p links=%d yeni %d | codes=%s",
                DEFAULT_ROLES.keys(),
                len(created_roles),
                len(created_roles) * len(DEFAULT_ROLES),
                created_links,
                sorted(codes),
            )
    except SQLAlchemyError:
        logger.exception("seed_roles başarısız")
        raise
    finally:
        await state.aclose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true",
        help="role_permissions tablosunu boşalt (mevcut kullanıcı yetkileri dokunulmaz).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s :: %(message)s")
    asyncio.run(seed_roles(reset=args.reset))


if __name__ == "__main__":
    main()

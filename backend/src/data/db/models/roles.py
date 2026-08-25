"""Role + Permission skeleton.

LDAP group_dn → role mapping için gerekli. Üç bileşen:

- ``permissions``: global izinler (örn. ``ADMIN``, ``REQUEST_VIEW``).
- ``roles``: permission setleri (admin/editor/viewer/redteam_operator).
- ``role_permissions``: role ↔ permission M:N.

Seeding idempotent: ``seed_admin`` script'i script_tekrar çalıştırıldığında
``ON CONFLICT DO NOTHING`` ile davranır (named-key).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permissions_code"),)

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False, server_default="now()")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),
    )

    role_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True,
    )
    permission_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True,
    )


__all__ = ["Permission", "Role", "RolePermission"]

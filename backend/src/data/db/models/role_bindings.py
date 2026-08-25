"""`role_bindings` — bir kullanıcıya bir org/namespace'te bir rol.

LDAP senkronizasyonu burada ``source='ldap'`` ile yazılır; manual
grants ``source='manual'``. Sync revoke yalnızca LDAP satırlarına
dokunur (kılavuz §4.4 invariant: "manual grants survive").

``namespace_id`` NULL → org-wide.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


# Source sabitleri — kod içinde literal dağılmasını engeller.
class RoleBindingSource:
    MANUAL = "manual"
    LDAP = "ldap"

    _ALL = (MANUAL, LDAP)


class OrgMembership(Base):
    """Kullanıcının org üyeliği. Bilinçli olarak (binding'den ayrıştırılır):
    bir kullanıcı bir org'a ait olabilir ama henüz hiçbir role bağlı
    olmayabilir (``DEFAULT_NAMESPACE_SLUG`` viewport'ı buna dayanır).
    """

    __tablename__ = "org_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_org_memberships_user_org"),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    org_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    created_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False, server_default="now()")


class RoleBinding(Base):
    __tablename__ = "role_bindings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "role_id", "org_id", "namespace_id",
            name="uq_role_bindings_user_role_org_ns",
        ),
        CheckConstraint(
            "source IN ('manual', 'ldap')", name="ck_role_bindings_source",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    role_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    org_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    namespace_id: Mapped[Optional[Uuid]] = mapped_column(
        Uuid, ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=True,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=RoleBindingSource.MANUAL)

    created_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False, server_default="now()")


class LdapGroupMapping(Base):
    """LDAP group DN → role/org/namespace eşlemesi.

    ``memberOf`` claim'i her login'de authoritative olarak değerlendirilir;
    eşleşen satırlar ``role_bindings`` üretir/iptal eder.
    """

    __tablename__ = "ldap_group_mappings"
    __table_args__ = (
        UniqueConstraint(
            "group_dn", "role_id", "org_id", "namespace_id",
            name="uq_ldap_group_mappings_dn_role_org_ns",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    group_dn: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    role_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    org_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    namespace_id: Mapped[Optional[Uuid]] = mapped_column(
        Uuid, ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=True,
    )

    created_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False, server_default="now()")
    updated_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False, server_default="now()")


__all__ = [
    "LdapGroupMapping",
    "OrgMembership",
    "RoleBinding",
    "RoleBindingSource",
]

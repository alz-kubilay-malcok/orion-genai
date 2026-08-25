"""Organization + Namespace skeleton (LDAP role binding scope'ları için).

`organization` ve `namespace` LDAP provisioning scope'unun doğal parçası;
admin panel tek-tenant çalıştığı için minimal iskelet yeterli:
- INSERT/SELECT-only, performans indekslenir.
- FK referans bütünlüğü seed sırasında zorlanır.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default="now()",
    )
    updated_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default="now()",
    )


class Namespace(Base):
    __tablename__ = "namespaces"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_namespaces_org_slug"),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    org_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default="now()",
    )


__all__ = ["Organization", "Namespace"]

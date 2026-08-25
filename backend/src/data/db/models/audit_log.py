"""`audit_log` — append-only audit kaydı (kılavuz §5 admin LDAP mapping
endpoint'leri).

`audit_events` tablusundan (request_id FK'li) farklıdır: burada
``request_id`` opsiyonel; mapping CRUD (group_dn ↔ role ↔ namespace)
gibi request-bound olmayan aksiyonları da kapsar.

Append-only invariant: repo/handler'da delete/update çağrısı
yapılmaz.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JsonEncodedDict, UtcDateTime, Uuid


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64))
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JsonEncodedDict, nullable=True,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default="now()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AuditLog id={self.id!r} action={self.action!r} "
            f"actor={self.actor_id!r} target={self.target_type}:{self.target_id!r}>"
        )


__all__ = ["AuditLog"]

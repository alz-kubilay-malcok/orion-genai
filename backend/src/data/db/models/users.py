"""`User` ORM modeli (LDAP-aware).

- Local bcrypt kullanıcı: ``password_hash`` dolu.
- LDAP kullanıcı: ``password_hash`` NULL — parola directory'de, **asla**
  DB'ye yazılmaz (kılavuz invariant).
- ``ldap_dn`` provisioning join key. NULL olan satır local-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class User(Base):
    __tablename__ = "users"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ldap_dn: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Yalnızca local hesaplara set; LDAP'tan gelen kullanıcılarda kalıcı NULL
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)

    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["User"]

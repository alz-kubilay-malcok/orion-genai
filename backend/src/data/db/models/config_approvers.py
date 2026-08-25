"""ConfigApprover ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class ConfigApprover(Base):
    __tablename__ = "config_approvers"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('GENAI_APPROVAL','CHATBOT_ASSIGNMENT')",
            name="config_approvers_scope_check",
        ),
        UniqueConstraint(
            "email", "scope", name="config_approvers_email_scope_uidx",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["ConfigApprover"]

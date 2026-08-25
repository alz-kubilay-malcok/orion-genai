"""AuditEvent ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JsonText, UtcDateTime, Uuid


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("requests.id", ondelete="RESTRICT"), nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(Text)
    request_version: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[str] = mapped_column(
        "metadata", JsonText, nullable=False, server_default="{}",
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["AuditEvent"]

"""RequestRevision ORM model (revize-diff snapshot tablosu)."""

from __future__ import annotations

from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JsonText, UtcDateTime, Uuid


class RequestRevision(Base):
    __tablename__ = "request_revisions"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "version",
            name="request_revisions_request_version_uidx",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(JsonText, nullable=False, server_default="{}")
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False,
    )


__all__ = ["RequestRevision"]

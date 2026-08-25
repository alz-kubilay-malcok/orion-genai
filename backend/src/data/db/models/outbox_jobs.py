"""OutboxJob ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JsonText, OUTBOX_STATUS, UtcDateTime, Uuid, TzOptionalDateTime


class OutboxJob(Base):
    __tablename__ = "outbox_jobs"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0", name="outbox_jobs_attempts_check",
        ),
        CheckConstraint(
            "max_attempts >= 1", name="outbox_jobs_max_attempts_check",
        ),
        CheckConstraint(
            "(status = 'processing' AND lease_owner IS NOT NULL "
            "AND leased_until IS NOT NULL) OR status <> 'processing'",
            name="outbox_jobs_lease_check",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="request",
    )
    aggregate_id: Mapped[Optional[Uuid]] = mapped_column(
        Uuid, ForeignKey("requests.id", ondelete="CASCADE"),
    )
    payload: Mapped[str] = mapped_column(JsonText, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        OUTBOX_STATUS, nullable=False, server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    available_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    lease_owner: Mapped[Optional[str]] = mapped_column(Text)
    leased_until: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    last_error_code: Mapped[Optional[str]] = mapped_column(Text)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    completed_at: Mapped[Optional[TzOptionalDateTime]] = mapped_column(
        TzOptionalDateTime,
    )


__all__ = ["OutboxJob"]

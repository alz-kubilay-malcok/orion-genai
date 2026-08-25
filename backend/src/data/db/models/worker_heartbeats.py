"""WorkerHeartbeat ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    last_seen_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    active_job_id: Mapped[Optional[Uuid]] = mapped_column(Uuid)
    scheduler_last_run_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)


__all__ = ["WorkerHeartbeat"]

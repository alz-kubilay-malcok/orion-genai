"""ApprovalToken ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class ApprovalToken(Base):
    __tablename__ = "approval_tokens"
    __table_args__ = (
        CheckConstraint(
            "action IN ('approve','revise','reject')",
            name="approval_tokens_action_check",
        ),
        CheckConstraint(
            "expires_at > issued_at", name="approval_tokens_expiry_check",
        ),
        UniqueConstraint(
            "token_hash", name="approval_tokens_hash_uidx",
        ),
        UniqueConstraint(
            "request_id", "action", name="approval_tokens_request_action_uidx",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    issued_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    used_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    invalidated_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    invalidation_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["ApprovalToken"]

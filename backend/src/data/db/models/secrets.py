"""Secret ORM model."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class Secret(Base):
    __tablename__ = "secrets"
    __table_args__ = (
        CheckConstraint(
            "secret_type IN ('litellm_key','mcp_key')",
            name="secrets_type_check",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("requests.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    secret_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider_token_id: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    auth_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_hint: Mapped[str] = mapped_column(String(4), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["Secret"]

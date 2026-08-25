"""MailMessage ORM model.

`read_by_user_id` intikam FK'sız — auth strip sonrası `users` tablosu
yok, LDAP gelince yeniden bağlanacak.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JsonEncodedList, UtcDateTime, Uuid, TzOptionalDateTime


class MailMessage(Base):
    __tablename__ = "mail_messages"
    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('pending','sent','failed','skipped')",
            name="mail_messages_delivery_status_check",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[Optional[Uuid]] = mapped_column(
        Uuid, ForeignKey("requests.id", ondelete="SET NULL"),
    )
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    from_email: Mapped[str] = mapped_column(Text, nullable=False)
    recipients: Mapped[list[str]] = mapped_column(JsonEncodedList, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    body_html: Mapped[Optional[str]] = mapped_column(Text)
    has_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(Text)
    app_env: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="skipped",
    )
    read_at: Mapped[Optional[TzOptionalDateTime]] = mapped_column(
        TzOptionalDateTime,
    )
    read_by_user_id: Mapped[Optional[Uuid]] = mapped_column(Uuid)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default="now()",
    )


__all__ = ["MailMessage"]

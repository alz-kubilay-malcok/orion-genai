"""ConfigMCPTool ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class ConfigMCPTool(Base):
    __tablename__ = "config_mcp_tools"
    __table_args__ = (
        UniqueConstraint(
            "server_id", "tool_name", name="config_mcp_tools_server_tool_uidx",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    server_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("config_mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    input_schema: Mapped[Optional[str]] = mapped_column(Text)
    evaluation_score: Mapped[Optional[int]] = mapped_column(Integer)
    evaluation_id: Mapped[Optional[str]] = mapped_column(Text)
    evaluation_verified_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    metadata_json: Mapped[str] = mapped_column(
        "metadata", Text, nullable=False, server_default="{}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    discovered_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["ConfigMCPTool"]

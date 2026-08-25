"""ConfigMCPServer ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, Uuid


class ConfigMCPServer(Base):
    __tablename__ = "config_mcp_servers"
    __table_args__ = (
        UniqueConstraint(
            "environment", "slug", name="config_mcp_servers_env_slug_uidx",
        ),
        UniqueConstraint(
            "environment", "endpoint_url", name="config_mcp_servers_env_endpoint_uidx",
        ),
        CheckConstraint(
            "transport = 'streamable_http'", name="config_mcp_servers_transport_check",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    department_name: Mapped[str] = mapped_column(Text, nullable=False)
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    technical_owner_email: Mapped[str] = mapped_column(Text, nullable=False)
    purpose_text: Mapped[str] = mapped_column(Text, nullable=False)
    repo_platform: Mapped[str] = mapped_column(String(16), nullable=False)
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    devops_jira_key: Mapped[Optional[str]] = mapped_column(Text)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    transport: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="streamable_http",
    )
    minimum_evaluation_score: Mapped[Optional[int]] = mapped_column(Integer)
    allows_all_tools: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    gateway_server_id: Mapped[Optional[str]] = mapped_column(Text)
    gateway_sync_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending",
    )
    gateway_synced_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)
    last_discovered_at: Mapped[Optional[UtcDateTime]] = mapped_column(UtcDateTime)

    source_request_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("requests.id"), nullable=False,
    )

    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["ConfigMCPServer"]

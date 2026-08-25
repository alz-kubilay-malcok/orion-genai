"""Request ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import (
    ENVIRONMENT,
    JsonEncodedList,
    JsonText,
    REPO_PLATFORM,
    REQUEST_STATUS,
    REQUEST_TYPE,
    UtcDateTime,
    Uuid,
    TzOptionalDateTime,
)


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        UniqueConstraint(
            "genai_orion_panel_ticket_id", "request_type",
            name="requests_ticket_type_uidx",
        ),
        CheckConstraint(
            "estimated_daily_requests IS NULL OR estimated_daily_requests > 0",
            name="requests_daily_requests_check",
        ),
        CheckConstraint(
            "max_concurrent_requests IS NULL OR max_concurrent_requests >= 1",
            name="requests_concurrency_check",
        ),
        CheckConstraint(
            "tpm_approved IS NULL OR tpm_approved > 0",
            name="requests_tpm_check",
        ),
        CheckConstraint(
            "rpm_approved IS NULL OR rpm_approved > 0",
            name="requests_rpm_check",
        ),
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    request_type: Mapped[str] = mapped_column(REQUEST_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(REQUEST_STATUS, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    genai_orion_panel_ticket_id: Mapped[str] = mapped_column(Text, nullable=False)
    genai_orion_panel_ticket_url: Mapped[str] = mapped_column(Text, nullable=False)
    requester_name: Mapped[str] = mapped_column(Text, nullable=False)
    requester_email: Mapped[str] = mapped_column(Text, nullable=False)
    genai_orion_panel_created_at: Mapped[UtcDateTime] = mapped_column(UtcDateTime, nullable=False)
    raw_genai_orion_panel_payload: Mapped[str] = mapped_column(JsonText, nullable=False)

    department_name: Mapped[Optional[str]] = mapped_column(Text)
    environment: Mapped[Optional[str]] = mapped_column(ENVIRONMENT)
    request_description: Mapped[Optional[str]] = mapped_column(Text)
    purpose_code: Mapped[Optional[str]] = mapped_column(Text)
    purpose_text: Mapped[Optional[str]] = mapped_column(Text)
    use_case: Mapped[Optional[str]] = mapped_column(Text)
    models: Mapped[Optional[list[str]]] = mapped_column(JsonEncodedList)
    response_window: Mapped[Optional[str]] = mapped_column(Text)
    usage_frequency: Mapped[Optional[str]] = mapped_column(Text)
    estimated_daily_requests: Mapped[Optional[int]] = mapped_column(Integer)
    max_concurrent_requests: Mapped[Optional[int]] = mapped_column(Integer)
    input_pages: Mapped[Optional[float]] = mapped_column(Numeric)
    output_pages: Mapped[Optional[float]] = mapped_column(Numeric)
    estimated_tokens_per_request: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_peak_rpm: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_peak_tpm: Mapped[Optional[int]] = mapped_column(Integer)
    tpm_approved: Mapped[Optional[int]] = mapped_column(Integer)
    rpm_approved: Mapped[Optional[int]] = mapped_column(Integer)
    key_alias: Mapped[Optional[str]] = mapped_column(Text)
    litellm_team_id: Mapped[Optional[str]] = mapped_column(Text)
    mcp_server_slug: Mapped[Optional[str]] = mapped_column(Text)
    mcp_tool_names: Mapped[Optional[list[str]]] = mapped_column(JsonEncodedList)
    all_tools: Mapped[Optional[bool]] = mapped_column(Boolean)
    registry_allows_all_tools: Mapped[Optional[bool]] = mapped_column(Boolean)
    mcp_server_display_name: Mapped[Optional[str]] = mapped_column(Text)
    project_name: Mapped[Optional[str]] = mapped_column(Text)
    technical_owner_email: Mapped[Optional[str]] = mapped_column(Text)
    repo_platform: Mapped[Optional[str]] = mapped_column(REPO_PLATFORM)
    repo_url: Mapped[Optional[str]] = mapped_column(Text)
    devops_jira_key: Mapped[Optional[str]] = mapped_column(Text)
    mcp_endpoint_url: Mapped[Optional[str]] = mapped_column(Text)
    minimum_evaluation_score: Mapped[Optional[int]] = mapped_column(Integer)
    additional_notes: Mapped[Optional[str]] = mapped_column(Text)
    brief: Mapped[Optional[str]] = mapped_column(Text)
    channel_or_use_case: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[Optional[str]] = mapped_column(Text)
    target_date: Mapped[Optional[str]] = mapped_column(DateTime(timezone=False))
    assignee_email: Mapped[Optional[str]] = mapped_column(Text)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )
    completed_at: Mapped[Optional[TzOptionalDateTime]] = mapped_column(
        TzOptionalDateTime,
    )


__all__ = ["Request"]

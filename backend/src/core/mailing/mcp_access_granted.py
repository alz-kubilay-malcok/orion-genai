"""Notification for verified access grants on an existing LiteLLM key."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Literal

from backend.src.core.mailing.mailer import send_mail

logger = logging.getLogger(__name__)
NotificationStatus = Literal["smtp_accepted", "recorded", "failed"]


def send_mcp_access_granted(
    *, recipient_email: str, key_alias: str, mcp_name: str,
    environment: str, test_message: bool = False,
) -> NotificationStatus:
    provider = os.getenv("MAIL_PROVIDER", "placeholder").strip().lower()
    prefix = "[TEST - no access changed] " if test_message else ""
    try:
        accepted = send_mail(
            recipients=[recipient_email],
            subject=f"{prefix}[GenAi] MCP access granted - {key_alias}",
            template_name="mcp_access_granted",
            inputs={
                "key_alias": key_alias,
                "mcp_name": mcp_name,
                "environment": environment,
                "completed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "test_message": test_message,
            },
        )
    except Exception as exc:
        logger.warning("MCP grant notification failed (%s)", type(exc).__name__)
        return "failed"
    if not accepted:
        return "failed"
    if provider in {"placeholder", "none", "log", "jsonfile"}:
        return "recorded"
    return "smtp_accepted"
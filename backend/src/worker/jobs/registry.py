"""MCP registry outbox job."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .common import _require_uuid
from .provision import complete_request

async def handle_register_mcp(*, session: AsyncSession, payload: dict) -> None:
    """Registry: env yoksa dry-run complete (secret yazılmaz)."""
    request_id = _require_uuid(payload, "request_id")
    await complete_request(
        session,
        request_id,
        dry_run=True,
        write_secret=False,
        extra={"registry": "dry-run"},
    )


"""MCP registry outbox job."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .common import _require_uuid
from .provision import complete_request

async def handle_register_mcp(*, session: AsyncSession, payload: dict) -> None:
    """Registry: env yoksa dry-run complete (secret yazılmaz)."""
    from sqlalchemy import select

    from ...data.db.models.requests import Request

    request_id = _require_uuid(payload, "request_id")
    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is not None and not (row.mcp_server_slug or "").strip():
        slug = (row.project_name or "").strip()
        if slug:
            row.mcp_server_slug = slug
            await session.flush()
    await complete_request(
        session,
        request_id,
        dry_run=True,
        write_secret=False,
        extra={"registry": "dry-run"},
    )


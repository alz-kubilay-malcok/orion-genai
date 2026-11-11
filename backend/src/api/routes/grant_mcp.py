"""Admin-only MCP grants for existing LiteLLM key aliases."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from backend.src.api.auth.dependencies import get_current_superuser
from backend.src.core.litellm.grant_mcp import McpGrantError, grant_mcp_access
from backend.src.core.mailing.mcp_access_granted import send_mcp_access_granted
from backend.src.data.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
GrantName = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=255, pattern=r"^[^\x00-\x1f\x7f]+$",
)]


class GrantMcpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_alias: GrantName
    mcp_name: GrantName
    environment: Literal["DEV", "TEST", "STG", "PROD"]
    recipient_email: EmailStr


@router.post("/grant-mcp")
async def grant_mcp(
    body: GrantMcpBody,
    user: Annotated[User, Depends(get_current_superuser)],
) -> dict[str, object]:
    try:
        result = await grant_mcp_access(
            key_alias=body.key_alias, mcp_name=body.mcp_name, environment=body.environment,
        )
    except McpGrantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    notification_status = await asyncio.to_thread(
        send_mcp_access_granted,
        recipient_email=str(body.recipient_email), key_alias=body.key_alias,
        mcp_name=body.mcp_name, environment=body.environment,
    )
    logger.info(
        "MCP grant completed by=%s environment=%s status=%s notification=%s",
        user.username, body.environment, result["status"], notification_status,
    )
    return {
        **result,
        "notification": {
            "status": notification_status,
            "recipient_email": str(body.recipient_email),
        },
    }
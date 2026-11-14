"""MCP grants authenticated by an admin token or Orion webhook signature."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from backend.src.api.auth.dependencies import get_current_superuser, get_current_user
from backend.src.api.routes.grant_mcp_aliases import ALIAS_MAPPING
from backend.src.api.routes.orion_webhook import webhook_signature_failure
from backend.src.core.litellm.grant_mcp import McpGrantError, grant_mcp_access
from backend.src.core.mailing.mcp_access_granted import send_mcp_access_granted

logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)


async def _grant_actor(request: Request) -> str:
    if "x-genai-orion-panel-signature" in request.headers:
        secret = os.getenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", "").strip()
        mode = os.getenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac").strip().lower()
        if not secret or mode != "hmac":
            raise HTTPException(503, "Orion webhook authentication is not configured for MCP grants")
        rejected = webhook_signature_failure(request, await request.body())
        if rejected is not None:
            raise HTTPException(401, "INVALID_WEBHOOK_SIGNATURE")
        return "orion-integration"

    credentials = await _bearer_scheme(request)
    if credentials is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    async with request.app.state.container.session_factory() as session:
        user = await get_current_user(request, credentials=credentials, session=session)
        user = await get_current_superuser(user)
        return user.username


def resolve_alias(alias: str) -> str:
    if alias in ALIAS_MAPPING:
        resolved = ALIAS_MAPPING[alias]
        logger.info("eski alias \u00e7evrildi: %s -> %s", alias, resolved)
        return resolved
    return alias


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
    actor: Annotated[str, Depends(_grant_actor)],
) -> dict[str, object]:
    resolved_alias = resolve_alias(body.key_alias)
    try:
        result = await grant_mcp_access(
            key_alias=resolved_alias, mcp_name=body.mcp_name, environment=body.environment,
        )
    except McpGrantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    notification_status = await asyncio.to_thread(
        send_mcp_access_granted,
        recipient_email=str(body.recipient_email), key_alias=resolved_alias,
        mcp_name=body.mcp_name, environment=body.environment,
    )
    logger.info(
        "MCP grant completed by=%s environment=%s status=%s notification=%s",
        actor, body.environment, result["status"], notification_status,
    )
    return {
        **result,
        "resolved_alias": resolved_alias,
        "notification": {
            "status": notification_status,
            "recipient_email": str(body.recipient_email),
        },
    }
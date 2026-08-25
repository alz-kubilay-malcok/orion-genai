"""GET /catalog/mcp-servers?ortam=TEST|PROD.

LiteLLM `GET /v1/mcp/server` + `GET /mcp-rest/tools/list` — anlık, DB yok.
TEST → LITELLM_*_DEV (aynı mapping key provision ile).
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.src.core.litellm.mcp_catalog import (
    LiteLLMCatalogError,
    list_mcp_servers_from_litellm,
)

router = APIRouter(tags=["catalog"])


@router.get("/mcp-servers")
async def list_active_mcp_servers(
    ortam: str = Query(pattern="^(TEST|PROD)$"),
) -> JSONResponse:
    """Sonuç (contract uyumlu):
        { ortam, servers: [ { server_name, tools: [tool_name, ...] } ] }
    """
    try:
        servers = await list_mcp_servers_from_litellm(ortam)
    except LiteLLMCatalogError as exc:
        return JSONResponse(
            status_code=exc.status,
            content={"error_code": exc.code, "detail": exc.message},
        )

    return JSONResponse(
        content={
            "ortam": ortam,
            "servers": [
                {"server_name": s.server_name, "tools": s.tools}
                for s in servers
            ],
        }
    )

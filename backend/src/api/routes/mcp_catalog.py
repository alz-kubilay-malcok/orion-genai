"""GET /catalog/mcp-servers?ortam=TEST|PROD (Bölüm 10.2).

- Auth kaldırıldı (LDAP'a taşınacak). Endpoint open.
- Sadece active, matching environment, server + tool.
- Stable sort: server display_name, server_name; tool display_name, tool_name.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from backend.src.adapters.postgres.mcp_catalog import SqlAlchemyMCPCatalogPort

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["catalog"])


@router.get("/mcp-servers")
async def list_active_mcp_servers(
    request: Request,
    ortam: str = Query(pattern="^(TEST|PROD)$"),
) -> JSONResponse:
    """Sonuç (contract uyumlu):
        { ortam, servers: [ { server_name, tools: [tool_name, ...] } ] }

    `display_name` ve `allows_all_tools` server-level **dönülmez**;
    admin UI bunları `requests` tablosundan okur, bu endpoint yalnızca
    form selectbox kaynağıdır.
    """
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        catalog = SqlAlchemyMCPCatalogPort(session)
        servers = await catalog.list_active_servers(ortam)

    return JSONResponse(
        content={
            "ortam": ortam,
            "servers": [
                {
                    "server_name": s.server_name,
                    "tools": [t.tool_name for t in s.tools],
                }
                for s in servers
            ],
        }
    )

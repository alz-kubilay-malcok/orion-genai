"""Legacy ``genai_orion_panel_adapters.postgres.mcp_catalog`` takma modülü.

Yerli ORM tabanlı ``SqlAlchemyMCPCatalogPort``. Davranış sözleşmesi:

* :meth:`list_active_servers(ortam)` → ``list[ServerWithTools]``.
* Sadece ``is_active=True`` ve ``environment=ortam`` olanları döner.
* Stable sort: server ``display_name`` + ``slug``; tool ``display_name`` + ``tool_name``.

Notlar:

* Tool kayıtları ``config_mcp_tools`` tablosundan ``server_id`` FK üzerinden
  çekilir; ``ConfigMCPTool.display_name`` selectbox'ta görünmüyor — bunu
  frontend sıralama düşüncesi için ORM'den alıyoruz.
* Bu katmanın yerine ``backend.src.adapters.catalog`` paketi sonraki
  refactor turunda açılacak.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.data.db.models.config_mcp_servers import ConfigMCPServer
from backend.src.data.db.models.config_mcp_tools import ConfigMCPTool


@dataclass(slots=True, frozen=True)
class ToolView:
    """Router için minimal tool view (hâlâ tüm tool isimleri)."""

    tool_name: str
    display_name: str


@dataclass(slots=True, frozen=True)
class ServerWithTools:
    """``list_active_servers`` dönüş elemanı."""

    server_name: str                     # slug
    display_name: str
    tools: list[ToolView] = field(default_factory=list)


class SqlAlchemyMCPCatalogPort:
    """Legacy port sözleşmesinin minimal ORM tabanlı implementasyonu."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_servers(self, ortam: str) -> list[ServerWithTools]:
        stmt = (
            select(ConfigMCPServer)
            .where(
                ConfigMCPServer.environment == ortam,
                ConfigMCPServer.is_active.is_(True),
            )
            .order_by(
                ConfigMCPServer.display_name.asc(),
                ConfigMCPServer.slug.asc(),
            )
        )
        result = await self._session.execute(stmt)
        servers = result.scalars().all()

        if not servers:
            return []

        server_ids = [s.id for s in servers]
        tool_stmt = (
            select(ConfigMCPTool)
            .where(ConfigMCPTool.server_id.in_(server_ids))
            .order_by(ConfigMCPTool.display_name.asc(),
                      ConfigMCPTool.tool_name.asc())
        )
        tools = (await self._session.execute(tool_stmt)).scalars().all()

        tools_by_server: dict = {sid: [] for sid in server_ids}
        for tool in tools:
            tools_by_server.setdefault(tool.server_id, []).append(
                ToolView(tool_name=tool.tool_name, display_name=tool.display_name)
            )

        out: list[ServerWithTools] = []
        for s in servers:
            out.append(
                ServerWithTools(
                    server_name=s.slug,
                    display_name=s.display_name,
                    tools=tools_by_server.get(s.id, []),
                )
            )
        return out


__all__ = ["SqlAlchemyMCPCatalogPort", "ServerWithTools", "ToolView"]

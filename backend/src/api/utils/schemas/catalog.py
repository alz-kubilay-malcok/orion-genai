"""MCP catalog GET response — contract uyumlu (Bölüm 5.3 / 10.2).

Net kilitlenmiş contract:
    { "servers": [ { "server_name": "xx", "tools": ["rag", "search"] } ] }

Bu endpoint'te `display_name` ya da `allows_all_tools` **dönülmez;
bunlar yalnızca iç admin UI / request detail tablosunda kullanılır**.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CatalogServer(BaseModel):
    """Catalog içindeki tek bir server descriptor (active + matching env)."""

    model_config = ConfigDict(extra="forbid")

    server_name: str = Field(min_length=1, max_length=128)
    tools: list[str]


class CatalogResponse(BaseModel):
    """`/catalog/mcp-servers?ortam=...` için kanonik response.

    `ortam` query'den response'a yazılır; tüketici kendi gönderdiği
    parametreyi echo olarak görebilir. Contract'ta wrapper olmasa da
    sorguyu echo'lamak test edilebilirlik için faydalı görüldü.
    """

    model_config = ConfigDict(extra="forbid")

    ortam: str = Field(pattern="^(TEST|PROD)$")
    servers: list[CatalogServer]

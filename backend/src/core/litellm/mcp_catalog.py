"""LiteLLM MCP katalog — anlık `GET /v1/mcp/server` + `GET /mcp-rest/tools/list`.

Orion form selectbox sözleşmesi:
    { ortam, servers: [ { server_name, tools: [tool_name, ...] } ] }
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from backend.src.core.litellm.target import resolve_litellm_http

logger = logging.getLogger("genai.litellm")

DEFAULT_SERVER_LIST_PATH = "/v1/mcp/server"
DEFAULT_TOOLS_LIST_PATH = "/mcp-rest/tools/list"


class LiteLLMCatalogError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class MCPServerCatalogItem:
    server_name: str
    tools: list[str] = field(default_factory=list)


def _join(base: str, path: str) -> str:
    path = path.strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    return f"{base.rstrip('/')}{path}"


def _as_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "servers", "mcp_servers", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _server_name(row: dict) -> str:
    for key in ("alias", "server_name", "slug", "display_name", "name", "server_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _identity_keys(row: dict) -> set[str]:
    keys: set[str] = set()
    for key in ("server_id", "alias", "server_name", "slug", "name"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            keys.add(value)
    return keys


def _tool_server_keys(tool: dict) -> set[str]:
    info = tool.get("mcp_info") if isinstance(tool.get("mcp_info"), dict) else {}
    keys: set[str] = set()
    for key in ("server_id", "alias", "server_name"):
        value = str(info.get(key) or "").strip().casefold()
        if value:
            keys.add(value)
    return keys


def _unprefix_tool(name: str, server_keys: set[str]) -> str:
    for key in server_keys:
        prefix = f"{key}-"
        if name.casefold().startswith(prefix):
            return name[len(prefix) :]
    return name


def _parse_tools_payload(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        tools = payload.get("tools")
        if isinstance(tools, list):
            return [row for row in tools if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
) -> object:
    logger.info("LiteLLM GET %s", url)
    try:
        response = await client.get(url, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
        logger.error("LiteLLM unreachable %s: %s", url, exc)
        raise LiteLLMCatalogError(
            502, "LITELLM_UNAVAILABLE", f"LiteLLM erişilemedi: {exc}"
        ) from exc
    logger.info("LiteLLM %s → HTTP %s", url, response.status_code)
    if response.status_code in {401, 403}:
        raise LiteLLMCatalogError(502, "LITELLM_AUTH", "LiteLLM kimlik doğrulama reddetti")
    if response.status_code >= 400:
        raise LiteLLMCatalogError(
            502,
            "LITELLM_UNAVAILABLE",
            f"LiteLLM HTTP {response.status_code}",
        )
    try:
        return response.json()
    except ValueError as exc:
        raise LiteLLMCatalogError(502, "LITELLM_UNAVAILABLE", "LiteLLM JSON dönmedi") from exc


async def list_mcp_servers_from_litellm(ortam: str) -> list[MCPServerCatalogItem]:
    """LiteLLM'den anlık MCP sunucu + tool listesi."""
    base, credential = resolve_litellm_http(ortam, kind="mcp")
    if not base or not credential:
        raise LiteLLMCatalogError(
            503,
            "LITELLM_NOT_CONFIGURED",
            "LITELLM_BASE_URL ve LITELLM_MASTER_KEY tanımlı değil",
        )

    server_path = (
        os.getenv("LITELLM_MCP_SERVER_LIST_PATH", DEFAULT_SERVER_LIST_PATH).strip()
        or DEFAULT_SERVER_LIST_PATH
    )
    tools_path = (
        os.getenv("LITELLM_MCP_TOOLS_LIST_PATH", DEFAULT_TOOLS_LIST_PATH).strip()
        or DEFAULT_TOOLS_LIST_PATH
    )
    headers = {"Authorization": f"Bearer {credential}"}
    timeout = float(os.getenv("LITELLM_MCP_CATALOG_TIMEOUT", "30") or "30")

    async with httpx.AsyncClient(timeout=timeout) as client:
        servers_payload = await _get_json(client, _join(base, server_path), headers)
        try:
            tools_payload = await _get_json(client, _join(base, tools_path), headers)
        except LiteLLMCatalogError:
            logger.warning("LiteLLM tools/list alınamadı; allowed_tools kullanılacak")
            tools_payload = {"tools": []}

    rows = _as_rows(servers_payload)
    live_tools = _parse_tools_payload(tools_payload)

    tools_by_server: dict[str, list[str]] = {}
    for tool in live_tools:
        raw_name = str(tool.get("name") or "").strip()
        if not raw_name:
            continue
        keys = _tool_server_keys(tool)
        name = _unprefix_tool(raw_name, keys)
        for key in keys:
            bucket = tools_by_server.setdefault(key, [])
            if name not in bucket:
                bucket.append(name)

    items: list[MCPServerCatalogItem] = []
    seen_names: set[str] = set()
    for row in rows:
        name = _server_name(row)
        if not name or name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())
        identities = _identity_keys(row)
        identities.add(name.casefold())
        tools: list[str] = []
        for key in identities:
            for tool_name in tools_by_server.get(key, []):
                if tool_name not in tools:
                    tools.append(tool_name)
        if not tools:
            tools = _str_list(row.get("allowed_tools") or row.get("tools"))
        items.append(MCPServerCatalogItem(server_name=name, tools=tools))

    items.sort(key=lambda item: (item.server_name.casefold(), item.server_name))
    return items


__all__ = [
    "LiteLLMCatalogError",
    "MCPServerCatalogItem",
    "list_mcp_servers_from_litellm",
]

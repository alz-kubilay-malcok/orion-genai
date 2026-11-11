"""Grant an existing virtual key MCP access without generating a new key."""

from __future__ import annotations

from typing import Any

import httpx

from backend.src.core.litellm.target import resolve_litellm_http

REQUIRED_ALIAS_PARTS = ("brysl", "brysel", "bireysel")
SERVER_LIST_KEYS = ("data", "servers", "mcp_servers", "result")
MAX_GRANT_ATTEMPTS = 3


class McpGrantError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


def has_required_part(alias: str) -> bool:
    folded = alias.replace("\u0130", "i").replace("\u0131", "i").casefold()
    return any(part in folded for part in REQUIRED_ALIAS_PARTS)


async def _request(
    client: httpx.AsyncClient, method: str, path: str,
    *, expect_json: bool = True, **kwargs: Any,
) -> Any:
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.RequestError as exc:
        raise McpGrantError(502, "LiteLLM is unreachable; check access before retrying") from exc
    if not response.is_success:
        raise McpGrantError(502, f"LiteLLM {path} returned HTTP {response.status_code}")
    if not expect_json:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise McpGrantError(502, f"LiteLLM {path} returned invalid JSON") from exc


def _info(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("info"), dict):
        raise McpGrantError(502, "LiteLLM returned invalid key information")
    return payload["info"]


def _server_rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload
    if isinstance(payload, dict):
        rows = None
        for key in SERVER_LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        raise McpGrantError(502, "LiteLLM returned an invalid MCP server list")
    return rows


def _permissions(info: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    permissions = info.get("object_permission")
    if permissions is None:
        permissions = {}
    if not isinstance(permissions, dict):
        raise McpGrantError(502, "LiteLLM returned invalid object permissions")
    servers = permissions.get("mcp_servers")
    if servers is None:
        servers = []
    if not isinstance(servers, list) or not all(isinstance(item, str) for item in servers):
        raise McpGrantError(502, "LiteLLM returned invalid MCP permissions")
    return permissions, servers


async def grant_mcp_access(
    *, key_alias: str, mcp_name: str, environment: str,
) -> dict[str, Any]:
    if not has_required_part(key_alias):
        raise McpGrantError(403, "Key alias must contain one of: BRYSL, BRYSEL, BIREYSEL")
    base, credential = resolve_litellm_http(environment, kind="litellm")
    if not base or not credential:
        raise McpGrantError(503, "LiteLLM is not configured for the requested environment")

    async with httpx.AsyncClient(
        base_url=base + "/", headers={"Authorization": f"Bearer {credential}"},
        timeout=30.0, trust_env=False,
    ) as client:
        servers = _server_rows(await _request(client, "GET", "/v1/mcp/server"))
        matches = [
            item for item in servers
            if mcp_name in (item.get("server_name"), item.get("alias"))
        ]
        if not matches:
            raise McpGrantError(404, "MCP server not found")
        if len(matches) != 1:
            raise McpGrantError(409, "MCP server name is ambiguous")
        server_id = matches[0].get("server_id")
        if not isinstance(server_id, str) or not server_id:
            raise McpGrantError(502, "LiteLLM returned an invalid MCP server ID")

        listed = await _request(
            client, "GET", "/key/list",
            params={"key_alias": key_alias, "return_full_object": "true"},
        )
        if not isinstance(listed, dict) or not isinstance(listed.get("keys"), list):
            raise McpGrantError(502, "LiteLLM returned an invalid key list")
        keys = [
            item for item in listed["keys"]
            if isinstance(item, dict) and item.get("key_alias") == key_alias
        ]
        if not keys:
            raise McpGrantError(404, "Key alias not found")
        if len(keys) != 1:
            raise McpGrantError(409, "Key alias is ambiguous")
        token = keys[0].get("token")
        if not isinstance(token, str) or not token:
            raise McpGrantError(502, "LiteLLM returned an invalid key token")

        wrote = False
        after: dict[str, Any] | None = None
        for _ in range(MAX_GRANT_ATTEMPTS):
            before = _info(await _request(client, "GET", "/key/info", params={"key": token}))
            permissions, current = _permissions(before)
            if server_id in current:
                after = before
                break
            updated = {
                name: value for name, value in permissions.items()
                if name != "object_permission_id"
            }
            updated["mcp_servers"] = sorted({*current, server_id})
            await _request(
                client, "POST", "/key/update",
                expect_json=False,
                json={"key": token, "object_permission": updated},
            )
            wrote = True
            after = _info(await _request(client, "GET", "/key/info", params={"key": token}))
            _, verified_servers = _permissions(after)
            if {*current, server_id}.issubset(verified_servers):
                break
        else:
            raise McpGrantError(502, "Update accepted but MCP access verification failed")
        if after is None:
            raise McpGrantError(502, "Update accepted but MCP access verification failed")
        return {
            "status": "granted" if wrote else "already_granted",
            "key_alias": key_alias,
            "mcp_name": mcp_name,
            "mcp_server_id": server_id,
            "environment": environment,
            "models": after.get("models"),
        }
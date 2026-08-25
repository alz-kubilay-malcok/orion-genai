"""LiteLLM Proxy `/key/generate` gövdesi.

Docs:
  https://docs.litellm.ai/docs/proxy/virtual_keys
  GenerateKeyRequest: `team_id`, `max_parallel_requests`, `models`, `key_alias`.

`max_parallel_requests`: eşzamanlı (in-flight) istek tavanı; aşınca 429.
`team_id`: key'i LiteLLM team satırına bağlar. UI "team adı" verir;
`GET /team/list` içinden `team_alias` veya `team_id` eşleşmesi çözülür.
TPM/RPM (`tpm_limit` / `rpm_limit`) bu üründe gönderilmez.
"""

from __future__ import annotations

from typing import Any, Mapping

TEAM_LIST_PATH = "/team/list"

# Orion form / DB değeri → LiteLLM proxy `model_name`.
# `text2test` katalog alias; proxy route `allianz-text`.
LITELLM_MODEL_ROUTES: dict[str, str] = {
    "text2test": "allianz-text",
}


def route_models_for_litellm(models: list[str] | None) -> list[str]:
    """LiteLLM'e gidecek model listesi. Alias'ları route eder, sırayı korur, tekilleştirir."""
    routed: list[str] = []
    seen: set[str] = set()
    for raw in models or []:
        name = str(raw).strip()
        if not name:
            continue
        mapped = LITELLM_MODEL_ROUTES.get(name.casefold(), name)
        if mapped in seen:
            continue
        seen.add(mapped)
        routed.append(mapped)
    return routed


def parse_team_list(payload: object) -> list[dict[str, Any]]:
    """`GET /team/list` hem `{teams: [...]}` hem düz liste dönebilir."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("teams", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def match_team_id(teams: list[Mapping[str, Any]], name: str) -> str | None:
    """`team_alias` veya `team_id` (casefold) → LiteLLM `team_id`."""
    needle = name.strip().casefold()
    if not needle:
        return None
    for team in teams:
        team_id = str(team.get("team_id") or "").strip()
        alias = str(
            team.get("team_alias") or team.get("team_name") or "",
        ).strip()
        if team_id.casefold() == needle or alias.casefold() == needle:
            return team_id or alias
    return None


def build_key_generate_body(
    *,
    key_alias: str,
    models: list[str] | None,
    team_id: str | None,
    max_parallel_requests: int | None,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """`POST /key/generate` JSON. TPM/RPM yok."""
    body: dict[str, object] = {
        "key_alias": key_alias,
        "models": route_models_for_litellm(list(models or [])),
        "metadata": dict(metadata or {}),
    }
    if team_id and team_id.strip():
        body["team_id"] = team_id.strip()
    if max_parallel_requests is not None:
        body["max_parallel_requests"] = int(max_parallel_requests)
    return body


# MCP key LLM modellerine düşmesin.
MCP_NO_LLM_MODELS = ["no-default-models"]
_LEGACY_MCP_KEY_PATHS = {"/mcp/keys/create", "/mcp/keys"}


def mcp_key_generate_path(raw: str | None) -> str:
    """Eski mock path `/mcp/keys/create` gerçek LiteLLM'de yok → `/key/generate`."""
    path = (raw or "").strip() or "/key/generate"
    if not path.startswith("/"):
        path = "/" + path
    if path.rstrip("/") in _LEGACY_MCP_KEY_PATHS:
        return "/key/generate"
    return path


def build_mcp_key_generate_body(
    *,
    key_alias: str,
    server_slug: str,
    tool_names: list[str] | None,
    all_tools: bool,
    metadata: Mapping[str, object] | None = None,
    team_id: str | None = None,
) -> dict[str, object]:
    """LiteLLM MCP scoped virtual key — `POST /key/generate`.

    https://docs.litellm.ai/docs/mcp_control
    """
    server = server_slug.strip()
    permission: dict[str, object] = {"mcp_servers": [server]}
    tools = [str(name).strip() for name in (tool_names or []) if str(name).strip()]
    if not all_tools and tools:
        permission["mcp_tool_permissions"] = {server: tools}
    body: dict[str, object] = {
        "key_alias": key_alias,
        "models": list(MCP_NO_LLM_MODELS),
        "object_permission": permission,
        "metadata": dict(metadata or {}),
    }
    if team_id and team_id.strip():
        body["team_id"] = team_id.strip()
    return body


__all__ = [
    "LITELLM_MODEL_ROUTES",
    "MCP_NO_LLM_MODELS",
    "TEAM_LIST_PATH",
    "build_key_generate_body",
    "build_mcp_key_generate_body",
    "match_team_id",
    "mcp_key_generate_path",
    "parse_team_list",
    "route_models_for_litellm",
]

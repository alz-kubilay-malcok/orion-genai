"""LiteLLM HTTP helpers — key generate body + live MCP catalog."""

from backend.src.core.litellm.generate_key import (
    LiteLLMKeyError,
    build_key_generate_body,
    build_mcp_key_generate_body,
    fetch_litellm_teams,
    generate_litellm_virtual_key,
    match_team_id,
    parse_team_list,
    route_models_for_litellm,
    teams_for_ui,
)
from backend.src.core.litellm.mcp_catalog import list_mcp_servers_from_litellm
from backend.src.core.litellm.target import resolve_litellm_http

__all__ = [
    "LiteLLMKeyError",
    "build_key_generate_body",
    "build_mcp_key_generate_body",
    "fetch_litellm_teams",
    "generate_litellm_virtual_key",
    "list_mcp_servers_from_litellm",
    "match_team_id",
    "parse_team_list",
    "resolve_litellm_http",
    "route_models_for_litellm",
    "teams_for_ui",
]

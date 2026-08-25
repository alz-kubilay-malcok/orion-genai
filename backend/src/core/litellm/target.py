"""LiteLLM / MCP gateway HTTP hedefi — env çözümü.

MCP form `TEST` = LiteLLM `DEV`. Ayrı `MCP_GATEWAY_*` varsa o kazanır;
yoksa aynı proxy (`LITELLM_BASE_URL` + `LITELLM_MASTER_KEY`).
"""

from __future__ import annotations

import os


def first_env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def litellm_env_for_ortam(ortam: str | None) -> str:
    env = (ortam or "DEV").upper()
    if env == "TEST":
        return "DEV"
    return env


def resolve_litellm_http(ortam: str | None, *, kind: str = "mcp") -> tuple[str, str]:
    """``(base_url, bearer)``. ``kind=litellm`` MCP_GATEWAY override kullanmaz."""
    litellm_env = litellm_env_for_ortam(ortam)
    litellm_base = first_env(f"LITELLM_BASE_URL_{litellm_env}", "LITELLM_BASE_URL")
    litellm_key = first_env(f"LITELLM_MASTER_KEY_{litellm_env}", "LITELLM_MASTER_KEY")
    if kind != "mcp":
        return litellm_base.rstrip("/"), litellm_key
    env = (ortam or "DEV").upper()
    base = first_env(f"MCP_GATEWAY_BASE_URL_{env}", "MCP_GATEWAY_BASE_URL") or litellm_base
    key = (
        first_env(f"MCP_GATEWAY_ADMIN_CREDENTIAL_{env}", "MCP_GATEWAY_ADMIN_CREDENTIAL")
        or litellm_key
    )
    return base.rstrip("/"), key


__all__ = ["first_env", "litellm_env_for_ortam", "resolve_litellm_http"]

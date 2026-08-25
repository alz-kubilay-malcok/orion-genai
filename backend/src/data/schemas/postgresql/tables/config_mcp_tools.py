"""`config_mcp_tools` — bir server'ın keşfedilen tool listesi."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS config_mcp_tools (
    id UUID PRIMARY KEY,
    server_id UUID NOT NULL REFERENCES config_mcp_servers(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    input_schema JSONB,
    evaluation_score INTEGER,
    evaluation_id TEXT,
    evaluation_verified_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    discovered_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT config_mcp_tools_server_tool_uidx UNIQUE (server_id, tool_name)
);

CREATE INDEX IF NOT EXISTS config_mcp_tools_active_idx
    ON config_mcp_tools (server_id, is_active, tool_name);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


config_mcp_tools_migration = Migration(version=6, name="config_mcp_tools", apply=apply)

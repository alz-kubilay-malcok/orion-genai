"""`config_mcp_tools` — server başına tool listesi."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS config_mcp_tools (
    id CHAR(36) PRIMARY KEY,
    server_id CHAR(36) NOT NULL REFERENCES config_mcp_servers(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    input_schema TEXT,
    evaluation_score INTEGER,
    evaluation_id TEXT,
    evaluation_verified_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 0,
    discovered_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT config_mcp_tools_server_tool_uidx UNIQUE (server_id, tool_name)
);

CREATE INDEX IF NOT EXISTS config_mcp_tools_active_idx
    ON config_mcp_tools (server_id, is_active, tool_name);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


config_mcp_tools_migration = Migration(version=6, name="config_mcp_tools", apply=apply)

"""`config_mcp_servers` — MCP server kaydı."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS config_mcp_servers (
    id CHAR(36) PRIMARY KEY,
    environment TEXT NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    department_name TEXT NOT NULL,
    project_name TEXT NOT NULL,
    technical_owner_email TEXT NOT NULL,
    purpose_text TEXT NOT NULL,
    repo_platform TEXT NOT NULL,
    repo_url TEXT NOT NULL,
    devops_jira_key TEXT,
    endpoint_url TEXT NOT NULL,
    transport TEXT NOT NULL DEFAULT 'streamable_http',
    minimum_evaluation_score INTEGER,
    allows_all_tools INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 0,
    gateway_server_id TEXT,
    gateway_sync_status TEXT NOT NULL DEFAULT 'pending',
    gateway_synced_at TEXT,
    last_discovered_at TEXT,
    source_request_id CHAR(36) NOT NULL REFERENCES requests(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT config_mcp_servers_env_slug_uidx UNIQUE (environment, slug),
    CONSTRAINT config_mcp_servers_env_endpoint_uidx UNIQUE (environment, endpoint_url),
    CONSTRAINT config_mcp_servers_environment_check CHECK (environment IN
        ('DEV', 'STG', 'TEST', 'PROD')),
    CONSTRAINT config_mcp_servers_repo_platform_check CHECK (repo_platform IN
        ('GITHUB', 'BITBUCKET')),
    CONSTRAINT config_mcp_servers_transport_check
        CHECK (transport = 'streamable_http'),
    CONSTRAINT config_mcp_servers_prod_min_score_check CHECK (
        environment <> 'PROD' OR minimum_evaluation_score >= 90
    )
);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


config_mcp_servers_migration = Migration(version=5, name="config_mcp_servers", apply=apply)

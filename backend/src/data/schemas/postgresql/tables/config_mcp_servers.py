"""`config_mcp_servers` — admin tarafından onaylanmış MCP server kaydı."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS config_mcp_servers (
    id UUID PRIMARY KEY,
    environment environment NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    department_name TEXT NOT NULL,
    project_name TEXT NOT NULL,
    technical_owner_email TEXT NOT NULL,
    purpose_text TEXT NOT NULL,
    repo_platform repo_platform NOT NULL,
    repo_url TEXT NOT NULL,
    devops_jira_key TEXT,
    endpoint_url TEXT NOT NULL,
    transport TEXT NOT NULL DEFAULT 'streamable_http',
    minimum_evaluation_score INTEGER,
    allows_all_tools BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    gateway_server_id TEXT,
    gateway_sync_status TEXT NOT NULL DEFAULT 'pending',
    gateway_synced_at TIMESTAMPTZ,
    last_discovered_at TIMESTAMPTZ,
    source_request_id UUID NOT NULL REFERENCES requests(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT config_mcp_servers_env_slug_uidx UNIQUE (environment, slug),
    CONSTRAINT config_mcp_servers_env_endpoint_uidx UNIQUE (environment, endpoint_url),
    CONSTRAINT config_mcp_servers_transport_check
        CHECK (transport = 'streamable_http'),
    CONSTRAINT config_mcp_servers_prod_min_score_check CHECK (
        environment <> 'PROD' OR minimum_evaluation_score >= 90
    )
);

-- PG-only partial unique indexes — aynı environment'da birden fazla aktif
-- satır olamaz.
CREATE UNIQUE INDEX IF NOT EXISTS config_mcp_servers_active_slug_uidx
    ON config_mcp_servers (environment, slug)
    WHERE is_active;
CREATE UNIQUE INDEX IF NOT EXISTS config_mcp_servers_active_endpoint_uidx
    ON config_mcp_servers (environment, endpoint_url)
    WHERE is_active;
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


config_mcp_servers_migration = Migration(version=5, name="config_mcp_servers", apply=apply)

"""`requests` tablosu — SQLite portable DDL."""

from __future__ import annotations

from ...registry import Migration

# UUID, ARRAY, JSONB yok: CHAR(36), JSON-encoded TEXT, JSON. ENUM
# yerine CHECK constraint.
DDL = """
CREATE TABLE IF NOT EXISTS requests (
    id CHAR(36) PRIMARY KEY,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    genai_orion_panel_ticket_id TEXT NOT NULL,
    genai_orion_panel_ticket_url TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    genai_orion_panel_created_at TEXT NOT NULL,
    raw_genai_orion_panel_payload TEXT NOT NULL,
    department_name TEXT,
    environment TEXT,
    request_description TEXT,
    purpose_code TEXT,
    purpose_text TEXT,
    use_case TEXT,
    models TEXT,
    response_window TEXT,
    usage_frequency TEXT,
    estimated_daily_requests INTEGER,
    max_concurrent_requests INTEGER,
    input_pages NUMERIC,
    output_pages NUMERIC,
    estimated_tokens_per_request INTEGER,
    estimated_peak_rpm INTEGER,
    estimated_peak_tpm INTEGER,
    tpm_approved INTEGER,
    rpm_approved INTEGER,
    key_alias TEXT,
    mcp_server_slug TEXT,
    mcp_tool_names TEXT,
    all_tools INTEGER,
    registry_allows_all_tools INTEGER,
    mcp_server_display_name TEXT,
    project_name TEXT,
    technical_owner_email TEXT,
    repo_platform TEXT,
    repo_url TEXT,
    devops_jira_key TEXT,
    mcp_endpoint_url TEXT,
    minimum_evaluation_score INTEGER,
    additional_notes TEXT,
    brief TEXT,
    channel_or_use_case TEXT,
    priority TEXT,
    target_date TEXT,
    assignee_email TEXT,
    reject_reason TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    CONSTRAINT requests_ticket_type_uidx UNIQUE (genai_orion_panel_ticket_id, request_type),
    CONSTRAINT requests_request_type_check CHECK (request_type IN
        ('litellm_key', 'mcp_key', 'mcp_server_registry', 'chatbot_support')),
    CONSTRAINT requests_environment_check CHECK (environment IS NULL OR environment IN
        ('DEV', 'STG', 'TEST', 'PROD')),
    CONSTRAINT requests_status_check CHECK (status IN
        ('received', 'waiting_approval', 'assigned',
         'provisioning', 'completed', 'rejected', 'failed', 'expired')),
    CONSTRAINT requests_repo_platform_check CHECK (repo_platform IS NULL OR repo_platform IN
        ('GITHUB', 'BITBUCKET')),
    CONSTRAINT requests_daily_requests_check
        CHECK (estimated_daily_requests IS NULL OR estimated_daily_requests > 0),
    CONSTRAINT requests_concurrency_check
        CHECK (max_concurrent_requests IS NULL OR max_concurrent_requests >= 1),
    CONSTRAINT requests_tpm_check
        CHECK (tpm_approved IS NULL OR tpm_approved > 0),
    CONSTRAINT requests_rpm_check
        CHECK (rpm_approved IS NULL OR rpm_approved > 0),
    CONSTRAINT requests_prod_min_score_check CHECK (
        request_type <> 'mcp_server_registry'
        OR environment <> 'PROD'
        OR minimum_evaluation_score >= 90
    )
);

CREATE INDEX IF NOT EXISTS requests_status_idx ON requests (status, updated_at);
CREATE INDEX IF NOT EXISTS requests_type_status_idx ON requests (request_type, status);
CREATE INDEX IF NOT EXISTS requests_requester_idx ON requests (requester_email, created_at);
CREATE INDEX IF NOT EXISTS requests_ticket_idx ON requests (genai_orion_panel_ticket_id);
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


requests_migration = Migration(version=2, name="requests", apply=apply)

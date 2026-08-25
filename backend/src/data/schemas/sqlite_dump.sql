-- =====================================================================
-- GenAiOrionPanel — SQLite şema dump
-- =====================================================================
-- Kaynak: backend/src/data/schemas/sqlite/tables/*.py
-- Sıra   : registry MIGRATIONS listesi (PG ile aynı sıra; enum/guard yok)
-- Versiyon: v15 (max). Yeni migration eklenirse sona append et, registry
--           sırası ile bu dump'un section sırası bire bir aynı olmalı.
--
-- Dialect farkları (PG vs SQLite)
--   - UUID          → CHAR(36)
--   - BYTEA         → BLOB
--   - VARCHAR(n)    → TEXT
--   - TIMESTAMPTZ   → ISO-8601 TEXT  (`UtcDateTime` normalize eder)
--   - JSONB         → TEXT (json-encoded)
--   - TEXT[]        → TEXT (json-encoded)
--   - ENUM          → CHECK constraint (values listesi inline)
--   - BOOLEAN       → INTEGER 0/1
--   - partial idx WHERE clause → SQLite 3.8+ destekler
--   - `assert_secret_request_type` trigger'ı SQLite'a PORTLANMAZ;
--     invariant `SecretRepository.insert_for_credential_request` tarafında.
-- =====================================================================


-- v1 — (enums SQLite'ta yok; CHECK constraint olarak ilgili tablolarda)
--     Atlandı; bkz. requests@mail_messages vb. CHECK'leri.

-- v2 — requests -----------------------------------------------------------
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


-- v3 — config_approvers ----------------------------------------------------
CREATE TABLE IF NOT EXISTS config_approvers (
    id CHAR(36) PRIMARY KEY,
    email TEXT NOT NULL,
    scope TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT config_approvers_scope_check
        CHECK (scope IN ('GENAI_APPROVAL', 'CHATBOT_ASSIGNMENT')),
    CONSTRAINT config_approvers_email_scope_uidx UNIQUE (email, scope)
);


-- v4 — worker_heartbeats ---------------------------------------------------
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active_job_id CHAR(36) NULL,
    scheduler_last_run_at TEXT NULL
);


-- v5 — config_mcp_servers --------------------------------------------------
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


-- v6 — config_mcp_tools ----------------------------------------------------
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


-- v7 — approval_tokens -----------------------------------------------------
CREATE TABLE IF NOT EXISTS approval_tokens (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,
    action TEXT NOT NULL,
    token_hash BLOB NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    invalidated_at TEXT,
    invalidation_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT approval_tokens_action_check
        CHECK (action IN ('approve', 'revise', 'reject')),
    CONSTRAINT approval_tokens_request_type_check CHECK (request_type IN
        ('litellm_key', 'mcp_key', 'mcp_server_registry', 'chatbot_support')),
    CONSTRAINT approval_tokens_expiry_check
        CHECK (expires_at > issued_at),
    CONSTRAINT approval_tokens_hash_uidx UNIQUE (token_hash),
    CONSTRAINT approval_tokens_request_action_uidx UNIQUE (request_id, action)
);

CREATE INDEX IF NOT EXISTS approval_tokens_request_idx
    ON approval_tokens (request_id);


-- v8 — secrets -------------------------------------------------------------
-- SQLite tarafında `Secret.repository.insert_for_credential_request`
-- invariant through uygular; PG'de olan `assert_secret_request_type`
-- trigger'ı SQLite'a portlanmaz.
CREATE TABLE IF NOT EXISTS secrets (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL UNIQUE REFERENCES requests(id) ON DELETE RESTRICT,
    secret_type TEXT NOT NULL,
    provider_token_id TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    nonce BLOB NOT NULL,
    auth_tag BLOB NOT NULL,
    key_hint CHAR(4) NOT NULL,
    key_version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT secrets_type_check
        CHECK (secret_type IN ('litellm_key', 'mcp_key'))
);


-- v9 — audit_events --------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_events (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL REFERENCES requests(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    request_version INTEGER NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS audit_events_request_idx
    ON audit_events (request_id, created_at);


-- v10 — outbox_jobs --------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_jobs (
    id CHAR(36) PRIMARY KEY,
    job_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL DEFAULT 'request',
    aggregate_id CHAR(36) REFERENCES requests(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL DEFAULT (datetime('now')),
    lease_owner TEXT,
    leased_until TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    CONSTRAINT outbox_jobs_status_check CHECK (status IN
        ('pending', 'processing', 'retry', 'completed', 'dead_letter')),
    CONSTRAINT outbox_jobs_attempts_check CHECK (attempts >= 0),
    CONSTRAINT outbox_jobs_max_attempts_check CHECK (max_attempts >= 1),
    CONSTRAINT outbox_jobs_lease_check CHECK (
        (status = 'processing' AND lease_owner IS NOT NULL
         AND leased_until IS NOT NULL)
        OR status <> 'processing'
    )
);

CREATE INDEX IF NOT EXISTS outbox_poll_idx
    ON outbox_jobs (available_at, created_at);
CREATE INDEX IF NOT EXISTS outbox_lease_recovery_idx
    ON outbox_jobs (leased_until)
    WHERE status = 'processing';


-- v11 — mail_messages ------------------------------------------------------
CREATE TABLE IF NOT EXISTS mail_messages (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) REFERENCES requests(id) ON DELETE SET NULL,
    template VARCHAR(64) NOT NULL,
    subject TEXT NOT NULL,
    from_email TEXT NOT NULL,
    recipients TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '{}',
    body_text TEXT,
    body_html TEXT,
    has_secret INTEGER NOT NULL DEFAULT 0,
    correlation_id TEXT,
    app_env VARCHAR(16) NOT NULL,
    delivery_status VARCHAR(16) NOT NULL DEFAULT 'skipped',
    read_at TEXT,
    read_by_user_id CHAR(36),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT mail_messages_delivery_status_check
        CHECK (delivery_status IN ('pending', 'sent', 'failed', 'skipped'))
);


-- v12 — request_revisions --------------------------------------------------
CREATE TABLE IF NOT EXISTS request_revisions (
    id CHAR(36) PRIMARY KEY,
    request_id CHAR(36) NOT NULL,
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT request_revisions_request_version_uidx UNIQUE (request_id, version)
);

CREATE INDEX IF NOT EXISTS request_revisions_request_idx
    ON request_revisions (request_id);


-- v13 — (secrets_request_type_guard SQLite'ta yok; app-side invariant)


-- v14 — mail_jwt_tokens ----------------------------------------------------
CREATE TABLE IF NOT EXISTS mail_jwt_tokens (
    id CHAR(36) PRIMARY KEY,
    jti TEXT NOT NULL,
    token_hash BLOB NOT NULL,
    request_id CHAR(36) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,
    action TEXT NOT NULL,
    recipient TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    revoked_at TEXT,
    revoked_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT mail_jwt_tokens_jti_uidx UNIQUE (jti),
    CONSTRAINT mail_jwt_tokens_hash_uidx UNIQUE (token_hash),
    CONSTRAINT mail_jwt_tokens_action_check
        CHECK (action IN ('approve', 'revise', 'reject')),
    CONSTRAINT mail_jwt_tokens_request_type_check
        CHECK (request_type IN ('litellm_key', 'mcp_key')),
    CONSTRAINT mail_jwt_tokens_expiry_check
        CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS mail_jwt_tokens_request_idx
    ON mail_jwt_tokens (request_id);

CREATE INDEX IF NOT EXISTS mail_jwt_tokens_active_expiry_idx
    ON mail_jwt_tokens (expires_at)
    WHERE used_at IS NULL AND revoked_at IS NULL;


-- v15 — (receivers kaldırıldı; v16 auth_security tarafından DROP TABLE)
-- holders DB kontratı LDAP gelmeden önce placeholder olarak eklendi;
-- karar (2026-08-24): LDAP users tablosu ile ikame, FK back-fill yok.

-- =====================================================================
-- v16 — auth_security ---------------------------------------------------------
-- v15 receivers tablosunu drop edip LDAP identity katmanını
-- (users / organizations / namespaces / roles / role_bindings /
-- ldap_group_mappings / audit_log) getirir. Registry MIGRATIONS list
-- ile senkron.

DROP TABLE IF EXISTS receivers;

CREATE TABLE IF NOT EXISTS organizations (
    id CHAR(36) PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS namespaces (
    id CHAR(36) PRIMARY KEY,
    org_id CHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_namespaces_org_slug UNIQUE (org_id, slug)
);
CREATE INDEX IF NOT EXISTS namespaces_org_idx ON namespaces (org_id);

CREATE TABLE IF NOT EXISTS permissions (
    id CHAR(36) PRIMARY KEY,
    code TEXT NOT NULL,
    description TEXT,
    CONSTRAINT uq_permissions_code UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS roles (
    id CHAR(36) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_roles_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id CHAR(36) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id CHAR(36) NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id),
    CONSTRAINT uq_role_permissions_role_perm UNIQUE (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id CHAR(36) PRIMARY KEY,
    username TEXT NOT NULL,
    ldap_dn TEXT,
    email TEXT NOT NULL,
    display_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_superuser INTEGER NOT NULL DEFAULT 0,
    password_hash TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT uq_users_ldap_dn UNIQUE (ldap_dn)
);
CREATE INDEX IF NOT EXISTS users_email_idx ON users (email);
CREATE INDEX IF NOT EXISTS users_ldap_dn_idx ON users (ldap_dn);

CREATE TABLE IF NOT EXISTS org_memberships (
    id CHAR(36) PRIMARY KEY,
    user_id CHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id CHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_org_memberships_user_org UNIQUE (user_id, org_id)
);
CREATE INDEX IF NOT EXISTS org_memberships_user_idx ON org_memberships (user_id);
CREATE INDEX IF NOT EXISTS org_memberships_org_idx ON org_memberships (org_id);

CREATE TABLE IF NOT EXISTS role_bindings (
    id CHAR(36) PRIMARY KEY,
    user_id CHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id CHAR(36) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    org_id CHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    namespace_id CHAR(36) REFERENCES namespaces(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_role_bindings_user_role_org_ns UNIQUE (user_id, role_id, org_id, namespace_id),
    CONSTRAINT ck_role_bindings_source CHECK (source IN ('manual', 'ldap'))
);
CREATE INDEX IF NOT EXISTS role_bindings_user_idx ON role_bindings (user_id);
CREATE INDEX IF NOT EXISTS role_bindings_role_idx ON role_bindings (role_id);
CREATE INDEX IF NOT EXISTS role_bindings_org_idx ON role_bindings (org_id);
CREATE INDEX IF NOT EXISTS role_bindings_namespace_idx ON role_bindings (namespace_id);

CREATE TABLE IF NOT EXISTS ldap_group_mappings (
    id CHAR(36) PRIMARY KEY,
    group_dn TEXT NOT NULL,
    role_id CHAR(36) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    org_id CHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    namespace_id CHAR(36) REFERENCES namespaces(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_ldap_group_mappings_dn_role_org_ns
        UNIQUE (group_dn, role_id, org_id, namespace_id)
);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_dn_idx ON ldap_group_mappings (group_dn);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_role_idx ON ldap_group_mappings (role_id);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_org_idx ON ldap_group_mappings (org_id);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_namespace_idx ON ldap_group_mappings (namespace_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id CHAR(36) PRIMARY KEY,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL DEFAULT 'user',
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    payload TEXT,
    correlation_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS audit_log_actor_idx ON audit_log (actor_id, created_at);
CREATE INDEX IF NOT EXISTS audit_log_action_idx ON audit_log (action);
CREATE INDEX IF NOT EXISTS audit_log_target_idx ON audit_log (target_type, target_id);
--
-- Bitti. v15 sonrası eklenen her migration burada VERSİYON sırasına
-- göre append edilmeli ve registry MIGRATIONS listesi ile senkron
-- tutulmalı.
-- =====================================================================

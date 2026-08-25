-- =====================================================================
-- GenAiOrionPanel — PostgreSQL şema dump
-- =====================================================================
-- Kaynak: backend/src/data/schemas/postgresql/tables/*.py
-- Sıra   : registry MIGRATIONS listesi (enums → tablolar → trigger)
-- Versiyon: v15 (max). Yeni migration eklenirse sona append et, registry
--           sırası ile bu dump'un section sırası bire bir aynı olmalı.
--
-- Bu dosya ORM-driven apply pipeline'ın (schemas.registry.Migration)
-- yansımasıdır; tek başına çalıştırılabilir değildir (idempotency
-- `_schema_history` ile sağlanıyor). Manuel / aşağı-akış replika
-- bootstrap'ında psql ile çalıştırılabilir.
-- =====================================================================


-- v1 — enums --------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE request_type AS ENUM (
        'litellm_key', 'mcp_key', 'mcp_server_registry', 'chatbot_support'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE environment AS ENUM ('DEV', 'STG', 'TEST', 'PROD');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE request_status AS ENUM (
        'received', 'waiting_approval', 'assigned',
        'provisioning', 'completed', 'rejected', 'failed', 'expired'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE repo_platform AS ENUM ('GITHUB', 'BITBUCKET');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE outbox_status AS ENUM (
        'pending', 'processing', 'retry', 'completed', 'dead_letter'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- v2 — requests -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS requests (
    id UUID PRIMARY KEY,
    request_type request_type NOT NULL,
    status request_status NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    genai_orion_panel_ticket_id TEXT NOT NULL,
    genai_orion_panel_ticket_url TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    genai_orion_panel_created_at TIMESTAMPTZ NOT NULL,
    raw_genai_orion_panel_payload JSONB NOT NULL,
    department_name TEXT,
    environment environment,
    request_description TEXT,
    purpose_code TEXT,
    purpose_text TEXT,
    use_case TEXT,
    models TEXT[],
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
    litellm_team_id TEXT,
    mcp_server_slug TEXT,
    mcp_tool_names TEXT[],
    all_tools BOOLEAN,
    registry_allows_all_tools BOOLEAN,
    mcp_server_display_name TEXT,
    project_name TEXT,
    technical_owner_email TEXT,
    repo_platform repo_platform,
    repo_url TEXT,
    devops_jira_key TEXT,
    mcp_endpoint_url TEXT,
    minimum_evaluation_score INTEGER,
    additional_notes TEXT,
    brief TEXT,
    channel_or_use_case TEXT,
    priority TEXT,
    target_date DATE,
    assignee_email TEXT,
    reject_reason TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT requests_ticket_type_uidx UNIQUE (genai_orion_panel_ticket_id, request_type),
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
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    scope TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT config_approvers_scope_check
        CHECK (scope IN ('GENAI_APPROVAL', 'CHATBOT_ASSIGNMENT')),
    CONSTRAINT config_approvers_email_scope_uidx UNIQUE (email, scope)
);


-- v4 — worker_heartbeats ---------------------------------------------------
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    active_job_id UUID,
    scheduler_last_run_at TIMESTAMPTZ
);


-- v5 — config_mcp_servers --------------------------------------------------
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


-- v6 — config_mcp_tools ----------------------------------------------------
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


-- v7 — approval_tokens -----------------------------------------------------
CREATE TABLE IF NOT EXISTS approval_tokens (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type request_type NOT NULL,
    action TEXT NOT NULL,
    token_hash BYTEA NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT approval_tokens_action_check
        CHECK (action IN ('approve', 'revise', 'reject')),
    CONSTRAINT approval_tokens_expiry_check
        CHECK (expires_at > issued_at),
    CONSTRAINT approval_tokens_hash_uidx UNIQUE (token_hash),
    CONSTRAINT approval_tokens_request_action_uidx UNIQUE (request_id, action)
);

CREATE INDEX IF NOT EXISTS approval_tokens_request_idx
    ON approval_tokens (request_id);

-- Sadece kullanılmamış, geçerli token'ların expiry sweep'ini hızlandırmak için.
CREATE INDEX IF NOT EXISTS approval_tokens_expiry_idx
    ON approval_tokens (expires_at)
    WHERE used_at IS NULL AND invalidated_at IS NULL;


-- v8 — secrets -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS secrets (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE REFERENCES requests(id) ON DELETE RESTRICT,
    secret_type TEXT NOT NULL,
    provider_token_id TEXT NOT NULL,
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    auth_tag BYTEA NOT NULL,
    key_hint CHAR(4) NOT NULL,
    key_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT secrets_type_check
        CHECK (secret_type IN ('litellm_key', 'mcp_key'))
);


-- v9 — audit_events --------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    request_version INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_events_request_idx
    ON audit_events (request_id, created_at);


-- v10 — outbox_jobs --------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_jobs (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL DEFAULT 'request',
    aggregate_id UUID REFERENCES requests(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    status outbox_status NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner TEXT,
    leased_until TIMESTAMPTZ,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT outbox_jobs_attempts_check CHECK (attempts >= 0),
    CONSTRAINT outbox_jobs_max_attempts_check CHECK (max_attempts >= 1),
    CONSTRAINT outbox_jobs_lease_check CHECK (
        (status = 'processing' AND lease_owner IS NOT NULL
         AND leased_until IS NOT NULL)
        OR status <> 'processing'
    )
);

-- Worker poll hot-path: pending/retry 'available_at <= now()' satırlar.
CREATE INDEX IF NOT EXISTS outbox_poll_idx
    ON outbox_jobs (available_at, created_at)
    WHERE status IN ('pending', 'retry');

-- Lease recovery (timed-out processing satırları için).
CREATE INDEX IF NOT EXISTS outbox_lease_recovery_idx
    ON outbox_jobs (leased_until)
    WHERE status = 'processing';


-- v11 — mail_messages ------------------------------------------------------
CREATE TABLE IF NOT EXISTS mail_messages (
    id UUID PRIMARY KEY,
    request_id UUID REFERENCES requests(id) ON DELETE SET NULL,
    template VARCHAR(64) NOT NULL,
    subject TEXT NOT NULL,
    from_email TEXT NOT NULL,
    recipients TEXT[] NOT NULL,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    body_text TEXT,
    body_html TEXT,
    has_secret BOOLEAN NOT NULL DEFAULT FALSE,
    correlation_id TEXT,
    app_env VARCHAR(16) NOT NULL,
    delivery_status VARCHAR(16) NOT NULL DEFAULT 'skipped',
    read_at TIMESTAMPTZ,
    read_by_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mail_messages_delivery_status_check
        CHECK (delivery_status IN ('pending', 'sent', 'failed', 'skipped'))
);


-- v12 — request_revisions --------------------------------------------------
CREATE TABLE IF NOT EXISTS request_revisions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL,
    version INTEGER NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT request_revisions_request_version_uidx UNIQUE (request_id, version)
);

CREATE INDEX IF NOT EXISTS request_revisions_request_idx
    ON request_revisions (request_id);


-- v13 — secrets_request_type_guard ----------------------------------------
-- secrets yalnız key requestleri için.
CREATE OR REPLACE FUNCTION assert_secret_request_type()
RETURNS TRIGGER AS $$
DECLARE
    req_type request_type;
BEGIN
    SELECT request_type INTO req_type FROM requests WHERE id = NEW.request_id;
    IF req_type NOT IN ('litellm_key', 'mcp_key') THEN
        RAISE EXCEPTION 'secrets yalnız litellm_key/mcp_key request_type için oluşturulabilir';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS secrets_request_type_guard ON secrets;
CREATE TRIGGER secrets_request_type_guard
    BEFORE INSERT OR UPDATE ON secrets
    FOR EACH ROW EXECUTE FUNCTION assert_secret_request_type();


-- v14 — mail_jwt_tokens ----------------------------------------------------
CREATE TABLE IF NOT EXISTS mail_jwt_tokens (
    id UUID PRIMARY KEY,
    jti VARCHAR(36) NOT NULL,
    token_hash BYTEA NOT NULL,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    request_type VARCHAR(32) NOT NULL,
    action TEXT NOT NULL,
    recipient TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
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

-- Replay sweep / temizlik için: hâlâ aktif olan token'ların süresi.
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
    id UUID PRIMARY KEY,
    slug VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS namespaces (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    slug VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_namespaces_org_slug UNIQUE (org_id, slug)
);
CREATE INDEX IF NOT EXISTS namespaces_org_idx ON namespaces (org_id);

CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    description VARCHAR(255),
    CONSTRAINT uq_permissions_code UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_roles_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id),
    CONSTRAINT uq_role_permissions_role_perm UNIQUE (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    ldap_dn VARCHAR(512),
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash VARCHAR(255),
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT uq_users_ldap_dn UNIQUE (ldap_dn)
);
CREATE INDEX IF NOT EXISTS users_email_idx ON users (email);
CREATE INDEX IF NOT EXISTS users_ldap_dn_idx ON users (ldap_dn);

CREATE TABLE IF NOT EXISTS org_memberships (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_org_memberships_user_org UNIQUE (user_id, org_id)
);
CREATE INDEX IF NOT EXISTS org_memberships_user_idx ON org_memberships (user_id);
CREATE INDEX IF NOT EXISTS org_memberships_org_idx ON org_memberships (org_id);

CREATE TABLE IF NOT EXISTS role_bindings (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    namespace_id UUID REFERENCES namespaces(id) ON DELETE CASCADE,
    source VARCHAR(16) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_role_bindings_user_role_org_ns UNIQUE (user_id, role_id, org_id, namespace_id),
    CONSTRAINT ck_role_bindings_source CHECK (source IN ('manual', 'ldap'))
);
CREATE INDEX IF NOT EXISTS role_bindings_user_idx ON role_bindings (user_id);
CREATE INDEX IF NOT EXISTS role_bindings_role_idx ON role_bindings (role_id);
CREATE INDEX IF NOT EXISTS role_bindings_org_idx ON role_bindings (org_id);
CREATE INDEX IF NOT EXISTS role_bindings_namespace_idx ON role_bindings (namespace_id);

CREATE TABLE IF NOT EXISTS ldap_group_mappings (
    id UUID PRIMARY KEY,
    group_dn VARCHAR(512) NOT NULL,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    namespace_id UUID REFERENCES namespaces(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ldap_group_mappings_dn_role_org_ns
        UNIQUE (group_dn, role_id, org_id, namespace_id)
);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_dn_idx ON ldap_group_mappings (group_dn);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_role_idx ON ldap_group_mappings (role_id);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_org_idx ON ldap_group_mappings (org_id);
CREATE INDEX IF NOT EXISTS ldap_group_mappings_namespace_idx ON ldap_group_mappings (namespace_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY,
    actor_id VARCHAR(255) NOT NULL,
    actor_type VARCHAR(32) NOT NULL DEFAULT 'user',
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id VARCHAR(64),
    payload JSONB,
    correlation_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_log_actor_idx ON audit_log (actor_id, created_at);
CREATE INDEX IF NOT EXISTS audit_log_action_idx ON audit_log (action);
CREATE INDEX IF NOT EXISTS audit_log_target_idx ON audit_log (target_type, target_id);

-- Bitti. v15 sonrası eklenen her migration burada VERSİYON sırasına
-- göre append edilmeli ve registry MIGRATIONS listesi ile senkron
-- tutulmalı.
-- =====================================================================

"""v16 — LDAP authentication: identity, role/permission/namespace scope,
group→role mappings, audit log, bootstrappers.

Bu migration aynı zamanda v15'te geçici olarak eklenen ``receivers``
tablosunu drop eder (user kararı — LDAP kullanıcı tablosu bunu ikame
eder).

Kılavuz cross-ref:
- Şema §4.3: users (username + ldap_dn + nullable password_hash),
  role_bindings.source, ldap_group_mappings.
- §4.6 prod gate bu tabloların ``_schema_history``'de görünmesini
  bekler (deploy sırası: registry sırası ile tutarlı).
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
-- Receivers düşür (LDAP ile ikame edildi).
DROP TABLE IF EXISTS receivers;

-- Organization + namespace skeleton.
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

-- Role + Permission.
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

-- Users (LDAP-aware). Nullable password_hash = directory kullanıcı.
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

-- Org üyeliği (role-binding'den bağımsız).
CREATE TABLE IF NOT EXISTS org_memberships (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_org_memberships_user_org UNIQUE (user_id, org_id)
);
CREATE INDEX IF NOT EXISTS org_memberships_user_idx ON org_memberships (user_id);
CREATE INDEX IF NOT EXISTS org_memberships_org_idx ON org_memberships (org_id);

-- Role bindings (kılavuz §4.3).
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

-- LDAP group → role mapping.
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

-- Append-only audit log (mapping CRUD ve authy olayları için).
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
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


auth_security_migration = Migration(version=16, name="auth_security", apply=apply)

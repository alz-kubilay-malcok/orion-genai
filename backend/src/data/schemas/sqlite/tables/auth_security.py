"""v16 — LDAP authentication: SQLite mirror.

Dialect farkları:
- UUID → CHAR(36) (types.Uuid normalize eder; PostgreSQL kütüphane
  tipi farkı yok — apply column'da yok)
- TIMESTAMPTZ → TEXT ISO-8601 (UtcDateTime normalize eder)
- JSONB → TEXT (json.dumps defaults utf-8 ascii)
- BOOLEAN → INTEGER (0/1) burada kabul ediyoruz: types.Boolean yok;
  `DbConfig`'a saygı.

UNIQUE constraint NULL davranışı: SQLite NULL'leri distinct sayar
(kılavuz notu — Postgres ile aynı). Service katmanı ``IS NULL``-aware
duplicate check yapıyor.
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
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
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.executescript(DDL)  # type: ignore[attr-defined]


auth_security_migration = Migration(version=16, name="auth_security", apply=apply)

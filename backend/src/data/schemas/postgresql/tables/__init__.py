"""Backend postgresql DDL registry.

Her tablo kendi modülünde; tek `Migration` objesi tanımlar (version, name,
apply). `apply(conn, dialect_name)` sync çalışır — asyncpg connection'ın
`.execute()`'ı ile uyumlu.

Enum tipler burada **bir kez** oluşturulur; tablolar enum tipine
referans verir (Postgres native `request_type`, `environment`, vb.).
"""

from __future__ import annotations

from ...registry import Migration
from .approval_tokens import approval_tokens_migration
from .audit_events import audit_events_migration
from .auth_security import auth_security_migration
from .config_approvers import config_approvers_migration
from .config_mcp_servers import config_mcp_servers_migration
from .config_mcp_tools import config_mcp_tools_migration
from .enums import enums_migration
from .mail_jwt_tokens import mail_jwt_tokens_migration
from .mail_messages import mail_messages_migration
from .outbox_jobs import outbox_jobs_migration
from .request_revisions import request_revisions_migration
from .requests import requests_migration
from .secrets import secrets_migration
from .secrets_request_type_guard import secrets_guard_migration
from .worker_heartbeats import worker_heartbeats_migration

# Sıra: önce enum'lar, sonra FK'ya muhtaç olmayanlar, sonra FK'lı olanlar.
# Trigger en sonda (secrets tablosuna bağlı). auth_security (v16) en sona
# — drop+create zincirinden etkilenmemesi için.
MIGRATIONS: list[Migration] = [
    enums_migration,
    requests_migration,
    config_approvers_migration,
    worker_heartbeats_migration,
    config_mcp_servers_migration,
    config_mcp_tools_migration,
    approval_tokens_migration,
    secrets_migration,
    audit_events_migration,
    outbox_jobs_migration,
    mail_messages_migration,
    request_revisions_migration,
    secrets_guard_migration,
    mail_jwt_tokens_migration,
    auth_security_migration,
]

__all__ = ["MIGRATIONS"]
